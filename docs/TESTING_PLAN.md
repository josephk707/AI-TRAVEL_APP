# Testing Plan
## AI Personalized Tourist Guide (TC-SO1)

Implements PRD §34 (Testing Strategy), re-tooled for the actual stack fixed in `IMPLEMENTATION_BLUEPRINT.md` §1 (Python/FastAPI backend, React Native/Expo mobile) rather than the PRD's Java/Spring-oriented tooling suggestions — the PRD names its recommended tools as illustrative of the *category* of testing required (§34's own framing: "Suggested Tooling"), not a fixed mandate, and explicitly lists Python+FastAPI as an approved alternative stack (§26.4). Every test type in the PRD's table is retained; only the tool names change to fit the chosen languages.

---

## 1. Test Type ↔ Tooling Mapping

| Test Type (PRD §34) | Focus | Tooling (this project) |
|---|---|---|
| Unit testing | Business-rule logic (§16), request/response mapping, utility functions | **pytest** (backend), **Jest + React Native Testing Library** (mobile) |
| Integration testing | Service-to-service and service-to-database interactions | **pytest + Testcontainers** (ephemeral Postgres+pgvector+PostGIS matching the production extensions) |
| API testing | Contract correctness, status codes, error handling for every FR endpoint | **httpx** (FastAPI's own recommended test client) for scripted cases + **schemathesis** (property-based, generates cases directly from the OpenAPI schema) for contract fuzzing |
| UI testing | Critical mobile flows — onboarding, itinerary creation, on-trip mode | **Jest + React Native Testing Library** (component level) |
| System / E2E testing | Full user journeys end-to-end, across real integrations in staging | **Maestro** (mobile E2E — chosen over Detox for lower config overhead in an Expo-managed workflow; Detox is a documented fallback if Maestro's flow coverage proves insufficient) |
| Regression testing | Re-run on every release to catch breakage in previously-working features | Full automated suite in CI; a tagged `@smoke` subset runs post-deploy (§32 Phase 8 exit criteria) |
| Performance testing | Itinerary-generation latency and API throughput under load (§15 targets) | **k6** |
| Security testing | Auth flows, input validation, dependency vulnerabilities | **OWASP ZAP** baseline scan (staging, pre-release) + **pip-audit**/**Dependabot** (dependency scanning in CI) + **gitleaks** (secret scanning) |
| Usability testing | Onboarding completion and core-flow comprehension with real users | Moderated sessions with a small user panel (manual, pre-launch and per major UX change) |
| User Acceptance Testing | Stakeholder sign-off against acceptance criteria (§14, §17) | Structured UAT checklist mapped to §42 traceability matrix — see §5 below |
| AI response evaluation | Narration accuracy, recommendation relevance, hallucination rate | Golden test sets + human review sampling + adversarial prompt tests — see §4 below |

---

## 2. CI Gating

Every pull request must pass, in order, before merge is allowed (mirrors `DEPLOYMENT_PLAN.md` §3.1):

```
lint → typecheck → unit tests → integration tests → API contract tests → security scan
```

`main` merges additionally trigger the mobile Jest suite and, on a nightly schedule (not per-PR, to keep PR feedback fast), the full Maestro E2E suite against a staging deploy plus the AI golden-set regression suite (§4). A release tag additionally requires the OWASP ZAP baseline scan and k6 performance run to pass against staging before production promotion.

---

## 3. Test Pyramid by Layer

### 3.1 Backend unit tests (pytest)

Target: every business rule in PRD §16 has at least one direct unit test, independent of any AI call (business rules are deterministic code, not LLM output — see `AI_ARCHITECTURE.md` §2 step 4: validation is explicitly "NOT delegated to the LLM").

| Rule under test | Example case |
|---|---|
| Budget tolerance | Itinerary at 111% of budget → flagged; at 109% → not flagged (10% tolerance, §16) |
| Opening-hours conflict | Item scheduled outside known hours → rejected/flagged `verify_on_arrival` |
| Overlap/pacing | Two items with overlapping time windows → rejected |
| Explicit-correction precedence | An `explicit_correction` signal always overrides a prior `inferred` weight, even if the inferred signal is more recent by write order (§16, §20) |
| Review eligibility | Review submission blocked unless a `completed` trip including that POI exists (mirrors the DB-level check in `DATABASE_SCHEMA.md` §6 — tested at both layers deliberately, since this is a trust-critical rule) |
| Reconciliation trade-off surfacing | Group preferences that conflict always produce a non-empty `conflicts[]`, never a silent pick (§16, FR-012) |

### 3.2 Integration tests (pytest + Testcontainers)

Spin up a real Postgres container with `pgvector` + `postgis` extensions enabled (matching `DATABASE_SCHEMA.md` §1 exactly) for every integration test run — RLS policies are tested against a real Postgres instance, not mocked, since RLS behavior cannot be meaningfully unit-tested in isolation.

| Scenario | Assertion |
|---|---|
| RLS: user A cannot read user B's `trips` row | Query as user A's JWT context returns zero rows for B's trip |
| RLS: trip member (not owner) can read but the invite-flow governs write | `trip_members` role enforcement |
| `is_trip_member()` helper function | Correct for owner, accepted member, non-member, and a member with `invite_status='declined'` |
| Memory-item retention job | Simulated clock: item within 14 days of expiry gets exactly one reminder, `deleted_at` is never set by the job (`DATABASE_SCHEMA.md` §6 contract) |
| Location-ping purge job | Pings older than 7 days on a `completed` trip are hard-deleted; pings on an `active` trip are untouched regardless of age |
| Heritage content publish atomicity | `is_published` only flips true after embeddings insert succeeds; a simulated embedding failure leaves `is_published=false` |

### 3.3 API contract tests (httpx + schemathesis)

- Scripted `httpx` tests cover every endpoint in `API_SPECIFICATION.md`, asserting: correct status codes, standard error envelope shape, auth-required-401, wrong-owner-403, and the specific business-rule `422` codes (`BUDGET_EXCEEDED`, `OUTSIDE_OPENING_HOURS`, `CLARIFICATION_NEEDED`, `POI_NOT_COVERED`, `IMAGE_UNUSABLE`, `REVIEW_NOT_ELIGIBLE`).
- `schemathesis` runs property-based fuzzing directly against the live OpenAPI schema in CI — catches contract drift (a field renamed in code but not in docs, an undocumented 500) automatically, without hand-writing every edge case.
- Idempotency-key behavior explicitly tested: same key + same payload → same response, no duplicate row created; same key + different payload → `409`.

### 3.4 Mobile component/unit tests (Jest + RNTL)

Focus on the logic the PRD explicitly calls out as user-facing correctness, not implementation detail:

- `tripUIMode` derivation (`MOBILE_ARCHITECTURE.md` §3) — correct mode for every `trip.status` value.
- Consent-gate components (location/camera pre-permission screens) render the benefit-specific copy before triggering the OS prompt.
- `ConfidenceBadge` renders visibly and distinctly for `confidence: "low"` vs `"high"` — a direct test of FR-008/FR-007's "never presented with the same certainty" business rule at the UI layer.
- Offline fallback: cached itinerary/heritage/phrasebook render read-only when `isOffline` is true, without crashing.

### 3.5 Mobile E2E (Maestro)

Full-journey flows, run nightly against staging:

1. Sign in (Google OAuth) → onboarding → home.
2. Create a trip → generate itinerary → conversational modification → view itinerary.
3. Simulate location updates (mocked GPS) → arrival notification appears → nearby recommendations shown.
4. Open heritage narration for a supported POI → ask a photo-based question → confidence badge renders correctly for both a high- and low-confidence fixture response.
5. Upload a memory-box photo → verify it appears in the gallery.
6. Submit a review after a completed trip; attempt to submit a review for a non-completed trip and confirm rejection.
7. Airplane-mode run: previously-downloaded itinerary/heritage/phrasebook remain viewable (Phase 2 feature, added to the suite once F26 ships).

---

## 4. AI Response Evaluation

The PRD calls this the "least off-the-shelf" part of the suite (§34) and requires it be held to the same rigor as the functional suite. Full pipeline detail is in `AI_ARCHITECTURE.md` §11; this section defines the testing mechanics.

### 4.1 Golden sets

| Golden set | Contents | Size at launch | Re-run trigger |
|---|---|---|---|
| Heritage narration | Known-correct fact/answer pairs per launch POI, authored and verified alongside the curated content itself (not written by the same person who wrote the content — independent verification, to avoid the same blind spot appearing in both) | 5–10 POIs × ~15–20 Q&A pairs each (§29.1 curated shortlist) | Every change to prompts, retrieval parameters (`AI_ARCHITECTURE.md` §5.2), or `heritage_content` |
| Itinerary generation | Fixed input scenarios (persona-derived — Meera solo, Weekend Squad group, Family Traveller) with expected budget/time/interest-fit assertions (not exact-output assertions, since itineraries are non-deterministic by design) | ~20 scenarios covering each persona from PRD §9 | Every change to the generation pipeline or business-rule validator |
| Visual Q&A | Fixture photo set per launch POI with expected grounded-answer topics + at least one deliberately ambiguous/low-confidence fixture per POI | ~5 photos × launch POIs | Every change to the Visual Q&A pipeline (`AI_ARCHITECTURE.md` §6) |
| Adversarial/guardrail | Off-topic requests, prompt-injection attempts embedded in trip notes/chat/photo questions, requests for unverified historical claims phrased as demands | ~30 cases, grown over time as real incidents are found | Every release |

### 4.2 Scoring & gate

- Golden-set pass criteria: narration/Q&A answers are scored against expected facts using a rubric (factually consistent / contradicts source / fabricates unsupported claim) — the last category is a **hard CI failure**, the first two are tracked as a trend metric, not necessarily a blocker, since paraphrase variation is expected and acceptable.
- A minimum pass bar is agreed before the first launch POI ships (§32 Phase 7 exit criteria: "AI narration accuracy meets the agreed bar for launch POIs") — exact numeric bar is a **Proposed Target, TBC** until the golden set exists to calibrate against, consistent with the PRD's own posture on unvalidated numeric targets (§39).

### 4.3 Human review sampling

Weekly sample of production `ai_messages` (stratified by `confidence` flag) reviewed manually against the same rubric — catches drift and novel failure modes the golden set doesn't yet cover. Findings that represent a new failure category are added back into the golden/adversarial sets (closing the loop).

### 4.4 Production AI-quality metrics (continuous, not a pre-release gate)

Hallucination-flag rate, "report an issue" volume on narration, and confidence-trend over time — dashboarded per `DEPLOYMENT_PLAN.md` §8, tied to the KPI table in PRD §37.

---

## 5. User Acceptance Testing — Traceability

This is the third leg of the PRD's Section 42 Requirement Traceability Matrix (BR ↔ FR ↔ User Story ↔ Acceptance Criteria ↔ **Test Scenario**). The FR↔endpoint mapping lives in `API_SPECIFICATION.md` §21 and the FR↔table mapping lives in `DATABASE_SCHEMA.md`; this table completes it with the concrete test scenario per BR, executed as a structured UAT checklist before each release that touches the feature.

| BR | Test Scenario | Test Type |
|---|---|---|
| BR-001 | Submit valid interests/budget/time/location → itinerary returned matching all four within tolerance | API + golden-set |
| BR-002 | Complete Google OAuth consent → land on home signed in; deny consent → no account created | E2E |
| BR-003 | Enter a planned stop's geofence on an active trip → arrival notification within target latency | Integration + E2E (mocked GPS) |
| BR-004 | Open narration for a supported POI → grounded content within target load time; unsupported POI → clear "not covered" message | API + golden-set |
| BR-005 | Photo of a recognizable detail → grounded answer; low-confidence case → visibly flagged | API + golden-set |
| BR-006 | Open phrasebook for a covered region → phrases with transliteration; works offline once downloaded | E2E (incl. airplane mode) |
| BR-007 | Upload completes → item appears in trip's memory box; item nears 12-month expiry → reminder sent before any deletion | Integration |
| BR-008 | Favourite a POI → appears under Favourites immediately; add to a named collection → appears only there | Unit + API |
| BR-009 | 2+ members submit differing preferences → itinerary reflects all input, conflicts visibly flagged | Integration |
| BR-010 | Submitted review passes moderation → appears on POI detail; non-completed-trip user attempts review → rejected | API |
| BR-011 | Time/budget/occasion submitted → 1–3-stop Quick Plan returned | API |
| BR-012 | Paste notes naming 2–3 places → those places appear in the generated plan | API + golden-set |
| BR-013 | Booking module interface is documented/stubbed | Architecture/interface-contract review (manual) |
| BR-014 | No location/camera access occurs without explicit consent recorded | Security/privacy review + integration test asserting a ping is rejected without a consent record |
| BR-015 | Trusted contact opens share link → sees live location for that trip only; SOS triggers → contact notified within target latency | E2E + API |
| BR-016 | Post-trip feedback submitted → next itinerary generation reflects at least one piece of that feedback | Integration (golden-set style before/after comparison) |
| BR-017 | Simulated POI closure on a monitored, active trip → adjustment proposed before the scheduled visit time; dismissal preserves the original plan | Integration |
| BR-018 | Log an expense → trip's actual-spend total updates immediately; crossing budget threshold → user notified | API |
| BR-019 | Complete onboarding → first itinerary reflects at least one selected interest | E2E + golden-set |

---

## 6. Performance Testing (k6)

| Scenario | Target (PRD §15, Proposed) |
|---|---|
| Itinerary generation, single request | 8–12s response time |
| Chat/modification reply | 3–5s response time |
| Concurrent itinerary-generation load | Ramp test to find the breaking point; concurrent-user target itself is TBC pending launch-scope decisions (§15), so this scenario's pass/fail bar is "no error-rate increase and no latency cliff below N concurrent users," with N set once a launch-scope figure exists |
| Location-ping throughput (active-trip simulation) | Sustained ping rate for a simulated cohort of concurrently-active trips, checked against arrival-notification latency target |

Run against staging before every release that touches the itinerary-generation or location-ping code paths, and on a scheduled cadence (Proposed Target: weekly) otherwise to catch infrastructure-level regressions.

---

## 7. Security Testing

- **OWASP ZAP baseline scan** against staging before each release — covers common web/API vulnerability classes (injection, broken auth, security misconfiguration).
- **Dependency scanning**: `pip-audit` (backend) and `npm audit`/Dependabot (mobile) run in CI on every PR; a known-critical CVE blocks merge.
- **Secret scanning**: `gitleaks` pre-commit hook + CI check, backed by GitHub push-protection.
- **Auth-flow specific tests**: token expiry/refresh correctness, RLS bypass attempts via crafted JWTs, rate-limit enforcement on AI endpoints (verifies the §27 "particularly AI endpoints — cost and abuse control" requirement is actually enforced, not just documented).
- **Consent/privacy review**: manual checklist confirming no location or camera data path exists that bypasses the explicit-consent gate described in `MOBILE_ARCHITECTURE.md` §5 and `API_SPECIFICATION.md` §6 — run once per release cycle that touches location/camera code, not just at launch.

---

## 8. Usability Testing

Moderated sessions with a small user panel (Proposed Target: 5–8 participants per round, standard usability-testing sample size for finding the majority of comprehension issues) at two points: once before Phase 1 launch (onboarding completion rate, core-flow comprehension against the §15 <6-screen onboarding target) and once after any major UX change to the dual-mode Planning/On-Trip system (§25.2). Findings feed back into `MOBILE_ARCHITECTURE.md` design-system iteration, not a one-time pre-launch checkbox.

---

## 9. Test Environment Data

- Staging is seeded with a fixed set of fixture trips, POIs, and the same curated launch heritage content used in the golden sets (§4.1) — so E2E and golden-set tests run against realistic, stable data rather than production-scale noise.
- No production user data is ever copied into staging (privacy-by-design, §27) — staging fixtures are synthetic or explicitly-consented test accounts only.
