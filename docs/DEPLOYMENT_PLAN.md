# Deployment Plan
## Environments, CI/CD, DevOps — AI Personalized Tourist Guide (TC-SO1)

Implements PRD §35 (Deployment & DevOps) and §36 (Monitoring & Maintenance) against the target stack fixed in `IMPLEMENTATION_BLUEPRINT.md` §1: FastAPI backend, Supabase (Postgres+pgvector+Storage+Auth), React Native + Expo mobile client.

---

## 1. Environments

Per PRD §35: "Development → Testing → Staging → Production, with no direct-to-production changes."

| Environment | Backend | Supabase project | Mobile |
|---|---|---|---|
| **Development** | Local FastAPI (`uvicorn --reload`) + local Supabase (Supabase CLI `supabase start`, Dockerized Postgres) | Local/ephemeral | Expo Go / dev client, pointed at local API |
| **Testing (CI)** | Ephemeral container, spun up per pipeline run | Ephemeral Postgres via Testcontainers (see `TESTING_PLAN.md`) | N/A (unit/component tests only, no live backend) |
| **Staging** | Deployed container, staging config | Dedicated Supabase **staging project** (separate from prod — never shares data) | EAS `staging` build profile, internal distribution (TestFlight internal / Play internal track) |
| **Production** | Deployed container, production config | Dedicated Supabase **production project** | EAS `production` build profile, public store releases + OTA updates |

A pull request can only reach staging after CI passes; staging can only promote to production after manual QA sign-off, matching the PRD's Phase 7→8 SDLC gate (§32: "Exit Criteria: Critical/high defects resolved; AI narration accuracy meets the agreed bar for launch POIs").

---

## 2. Hosting

| Component | Choice | Rationale |
|---|---|---|
| FastAPI backend | Containerized (Docker), deployed to a PaaS — **Render or Railway** for MVP, with a documented migration path to a managed container service (e.g. AWS ECS/Fly.io) if load requires it | PRD §26.4 "Alternative: PaaS... to minimise DevOps overhead" — the explicit lean-team path this project follows |
| Database + Auth + Storage | Supabase managed cloud (Postgres + pgvector + RLS + Auth + Storage) | Fixed architecture decision, `IMPLEMENTATION_BLUEPRINT.md` §1 |
| Mobile distribution | Expo Application Services (EAS) — Build, Submit, Update | Standard Expo-managed-workflow toolchain |

**Containerization (backend):**
```dockerfile
# Minimal shape — full Dockerfile lives in the repo once implementation starts
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-dev
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
Single image promoted unchanged across staging → production (build once, deploy the same artifact — never rebuild per environment) so "what was tested" and "what ships" are provably identical.

---

## 3. CI/CD Pipeline (GitHub Actions, per PRD §35)

### 3.1 Backend pipeline (`.github/workflows/backend.yml`)

```
on: pull_request, push to main
jobs:
  lint        → ruff / black --check
  typecheck   → mypy
  unit_test   → pytest tests/unit (see TESTING_PLAN.md §Unit)
  integration_test → pytest tests/integration, Testcontainers Postgres+pgvector
  api_contract_test → schemathesis against the OpenAPI schema (see TESTING_PLAN.md §API)
  security_scan → pip-audit / Dependabot alerts gate the merge
  build_image → docker build, push to registry tagged with commit SHA (main only)
  deploy_staging → auto-deploy on merge to main
  deploy_production → manual approval gate (GitHub Environments protection rule), promotes the
                       SAME image SHA already running in staging
```

### 3.2 Database migrations

```
on: push to main (migration files changed)
jobs:
  migration_dry_run → supabase db diff / lint against staging schema copy
  apply_staging → supabase migration up (staging project)
  apply_production → manual approval gate, same migration file, applied via
                      `supabase db push` — never a hand-run SQL console command
                      against production (PRD §35: "never manually against production")
```
Migrations are versioned, forward-only files under `supabase/migrations/`, matching `DATABASE_SCHEMA.md` §16.

### 3.3 Mobile pipeline (`.github/workflows/mobile.yml`)

```
on: pull_request → lint (eslint), typecheck (tsc), unit/component tests (jest)
on: push to main → eas build --profile staging (internal distribution)
on: tag release/* → eas build --profile production + eas submit (store review)
                     + eas update (OTA channel matching the release) for JS-only follow-up fixes
```

---

## 4. Secrets Management (§27, §35)

- No secret is ever hardcoded or committed — enforced by a pre-commit secret-scan hook (`gitleaks`) plus GitHub push-protection.
- Backend secrets (LLM API key, Google Maps server key, Weather API key, Translation API key, Supabase service-role key) live in the hosting platform's environment/secret store, injected at container runtime — never baked into the image.
- Mobile client secrets are limited to the **publishable** Supabase anon key and the **tile-rendering-scoped** Google Maps SDK key (see `MOBILE_ARCHITECTURE.md` §8) — both are safe-by-design for client exposure (RLS + domain/bundle restriction respectively); no server-side secret ever ships inside the mobile bundle.
- EAS Secrets store the mobile build-time environment values (API base URL per environment, publishable keys) per build profile.

---

## 5. Scheduled Jobs

Referenced from `DATABASE_SCHEMA.md`. Implemented as a lightweight scheduler (Supabase's built-in `pg_cron`, or the hosting platform's cron-job feature calling a dedicated FastAPI internal endpoint with a shared-secret header) — chosen at implementation time based on which is cheaper to operate; both are cron-equivalent, so this is a config-level, not architectural, decision.

| Job | Cadence | Behavior |
|---|---|---|
| Memory-box expiry reminder | Daily | Selects `memory_items` within 14 days of `retention_expires_at`, sends reminder notification, stamps `expiry_reminder_sent_at`. **Never sets `deleted_at`** — see `DATABASE_SCHEMA.md` §6 |
| Location-ping purge | Daily | Hard-deletes `location_pings` for completed/cancelled trips older than 7 days (§23 minimal-retention rule) |
| Personalization recompute | Daily (per active user, batched) | Recomputes `personalization_profile.preference_weights` from accumulated `feedback_signals` (§AI_ARCHITECTURE.md §7.1) — explicit corrections are NOT queued here, they write synchronously at request time |
| Weather cache refresh | Hourly, for destinations with a trip active in the next 72h | Keeps `weather_cache` warm for the Dynamic Re-Adaptation Engine (Phase 2) without a live call on every disruption check |
| Analytics rollup | Daily | Aggregates `analytics_events` into the KPI views consumed by `GET /admin/analytics/kpis` (§37) |

---

## 6. Data Deletion Workflow (§27 "users can request account and data deletion")

```
1. POST /auth/account/delete-request → writes an audit_logs entry, queues the request
   (never an immediate hard delete on the synchronous request path)
2. A reviewed deletion job runs on a defined SLA (Proposed Target: within 30 days, matching
   common data-protection norms — TBC pending legal input per PRD §23's own "TBC pending
   legal/financial input" framing for adjacent policy areas):
   - profiles row and all owned data cascades per FK `on delete cascade` (see DATABASE_SCHEMA.md)
   - memory_items in Supabase Storage are explicitly purged (storage objects don't auto-delete
     from a DB row delete — a cleanup step removes the objects, not just the metadata rows)
   - audit_logs entries about the deletion itself are retained (accountability trail, §27)
3. Confirmation notification sent once complete.
```
This is a workflow, not a single endpoint, because "never delete memory-box items silently" (§43.3) sets the product's general bar for any destructive action — deletion requests are deliberate, confirmed, and logged, never a background side effect of an unrelated job.

---

## 7. Rollback Strategy (§35)

- **Backend:** every deploy is a tagged, immutable image; rollback = redeploy the previous image tag (one-command revert on the PaaS). Blue-green is a documented future upgrade "once traffic justifies it" (§35), not required for MVP.
- **Database:** forward-only migrations mean rollback is a **new** forward migration that reverses the change, never a destructive `migration down` against production — protects against data loss from an automated down-migration touching live rows.
- **Mobile:** EAS Update allows an immediate OTA revert to the previous JS bundle for non-native issues; native-code issues require a new store submission (standard mobile constraint, mitigated by keeping native-module changes rare and heavily tested before release).

---

## 8. Monitoring & Observability (§36)

| Signal | Tooling | Notes |
|---|---|---|
| Application/API uptime + error rate | Hosting platform's built-in metrics + a status-page style healthcheck (`GET /healthz`) | Feeds the §15 99.5% uptime Proposed Target |
| Centralized error capture | Sentry (or equivalent) — frontend (Expo/Sentry RN SDK) and backend (Sentry Python SDK) | Single pane for both layers, matches §36 exactly |
| External API monitoring | Per-integration latency/error dashboards (Maps, Weather, LLM provider, Translation) | Catches a degraded provider before users report it (§36) |
| AI quality monitoring | Hallucination-flag rate (from `ai_messages.confidence`), "report an issue" volume on narration, confidence-trend over time | Dashboarded from `analytics_events` + `ai_messages`, ties to `AI_ARCHITECTURE.md` §11 |
| Performance | Response-time percentiles (p50/p95/p99) against §15 targets (itinerary gen 8–12s, chat 3–5s) | Platform APM or OpenTelemetry traces exported to the chosen backend |
| User analytics/funnel | onboarding → itinerary generated → trip started → trip completed (§36) | `analytics_events` rollups (§5 above) |
| Security monitoring | Auth failure-rate anomaly alerts (via Supabase Auth logs + backend rate-limit rejection logs) | §36 |
| Alerting | Threshold-based alerts (error rate, p99 latency, external-API failure rate) routed to a single on-call channel | Sized for a small team — lightweight severity levels, one triage owner, not an enterprise rotation (§36) |

---

## 9. Backups & Disaster Recovery (§15, §35)

- **Automated daily backups minimum** (Supabase managed automated backups, or `pg_dump` to Storage if the plan tier requires a manual schedule) — matches the PRD's explicit floor.
- **RPO/RTO:** Proposed Target — RPO ≤ 24h (daily backup cadence), RTO ≤ 4h for a full restore, both marked **TBC** per the PRD's own framing (§15: "RPO/RTO to be defined") until validated against the actual hosting tier's restore SLA.
- Backup restore is tested at least once before the production launch (a backup that has never been restored is not a verified backup) and periodically thereafter (Proposed Target: quarterly).

---

## 10. Incident Management (§36)

Lightweight, small-team-sized process, not an enterprise on-call rotation:

| Severity | Definition | Response |
|---|---|---|
| SEV-1 | Core service down (auth, itinerary generation, on-trip location) | Immediate triage by the on-duty engineer, status communicated, hotfix path bypasses normal PR-review SLA but never bypasses testing (§32 "no direct-to-production deploys") |
| SEV-2 | Degraded but functional (AI fallback mode active, one external API down) | Triaged same business day |
| SEV-3 | Non-critical bug, cosmetic issue, isolated edge case | Normal backlog |

---

## 11. Release Process (§33, §35)

1. Feature branch → PR → CI green (lint, typecheck, unit, integration, contract tests) → code review (no direct pushes to `main`, §33) → merge.
2. Merge to `main` auto-deploys to **staging** (backend) and produces a staging EAS build (mobile).
3. Sprint review demos against staging (§33).
4. Manual QA sign-off (functional + AI golden-set bar met, §32 Phase 7 exit criteria) gates promotion.
5. Manual-approval production deploy (same image, same migration) + tagged mobile release + EAS Update / store submission as appropriate.
6. Post-deploy smoke test suite runs against production (§32 Phase 8 exit criteria: "passes smoke tests").
