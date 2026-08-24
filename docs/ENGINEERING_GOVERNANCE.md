# Engineering Governance
## AI-Powered Personalized Tourist Guide & Travel Companion (TC-SO1)

This document is binding for all implementation work on this product. It does not replace the PRD or the derived engineering specifications — it governs *how* they get built.

---

## 1. Document Hierarchy

| Document | Role |
|---|---|
| `docs/AI_Tourist_Guide_Master_PRD_SDLC.pdf` | **Product source of truth.** Business requirements, functional requirements, business rules, scope. |
| `docs/IMPLEMENTATION_BLUEPRINT.md` | Implementation source of truth — feature-by-feature plan, phase roadmap. |
| `docs/DATABASE_SCHEMA.md` | Implementation source of truth — schema, RLS, migrations. |
| `docs/API_SPECIFICATION.md` | Implementation source of truth — endpoint contracts. |
| `docs/AI_ARCHITECTURE.md` | Implementation source of truth — AI/RAG pipelines. |
| `docs/MOBILE_ARCHITECTURE.md` | Implementation source of truth — client architecture. |
| `docs/DEPLOYMENT_PLAN.md` | Implementation source of truth — environments, CI/CD, ops. |
| `docs/TESTING_PLAN.md` | Implementation source of truth — test strategy per layer. |
| `docs/ARCHITECTURE_REVIEW.md` | Open findings against the above (2 CRITICAL, 7 HIGH, 15 MEDIUM, 11 LOW as of the last audit) — **check this before touching an area it flags.** |
| `docs/PHASE_STATUS.md` | Living record of what has actually been built, phase by phase. Created/updated at the end of every phase. |

**The derived engineering documents (Blueprint through Testing Plan) are the implementation source of truth unless an explicit, documented architecture decision overrides them.** Any such override must be recorded in the relevant document (or `PHASE_STATUS.md`'s "known limitations" if it's a scoped exception), not left implicit.

All eight documents above must be read — at minimum the sections relevant to the feature at hand — before implementing any major feature.

---

## 2. Engineering Objective

This is a complete, production-oriented application. It is explicitly **not**: a prototype, a static UI, a mockup, a proof of concept, a collection of disconnected screens, or a hardcoded demo.

A feature is not complete until its full path works end-to-end:

```
USER INTERFACE → API → BUSINESS LOGIC → DATABASE / EXTERNAL SERVICE → RESPONSE → USER INTERFACE
```

---

## 3. Core Principles

1. Never fake functionality.
2. Never replace required persistence with localStorage or hardcoded arrays.
3. Never create a button that claims to perform an action unless the action actually works.
4. Never claim an API integration works without testing it.
5. Never claim AI functionality works if the response is hardcoded.
6. Never expose secrets in frontend source code.
7. Never commit API keys.
8. Never trust client-provided user IDs when identity can be derived from authentication.
9. Enforce authorization server-side.
10. Respect database Row Level Security.
11. Validate all external API responses.
12. Validate AI structured outputs.
13. Handle loading, success, empty, and error states.
14. Never silently swallow errors.
15. Never silently change product requirements.
16. Never silently change architecture.
17. If the PRD is ambiguous, identify the ambiguity and document the decision.
18. Prefer maintainability over unnecessary complexity.
19. Do not introduce microservices unless justified by the architecture documents.
20. Do not implement future-phase functionality in a way that destabilizes the MVP.

---

## 4. AI Engineering Rules

- AI is a core product capability, not a bolt-on.
- AI must be implemented through proper service abstractions (`LLMGateway`, per `AI_ARCHITECTURE.md` §1) — never scatter direct LLM calls throughout the application.
- AI responses must use structured outputs where appropriate.
- Validate model responses before persisting or returning them.
- Use grounded retrieval (RAG) for factual heritage information — never present unsupported generated historical claims as verified fact.
- AI must receive only the context necessary for the task.
- User-specific information must be isolated by authenticated user (never cross-user context leakage).

---

## 5. Database Rules

- All persistent business data must be stored in the database — no silent fallback to local/in-memory state for anything that must survive a session.
- Use migrations for every schema change. Never modify production schema manually without a migration.
- Use foreign keys, appropriate indexes, and constraints.
- Use Row Level Security and enforce user ownership at the data layer.
- Every schema change must be documented (update `DATABASE_SCHEMA.md`, not just the migration file).

---

## 6. API Rules

Every API must:
- validate input
- authenticate where required
- authorize access
- return predictable responses
- return appropriate HTTP errors
- handle external failures gracefully
- have tests

Business logic belongs in service layers, not route handlers.

---

## 7. Mobile Rules

The mobile application must be responsive, accessible, visually polished, intuitive, performant, and production-oriented. Do not create generic dashboard-style interfaces — this should feel like a premium travel application. Planning Mode and On-Trip Mode (`MOBILE_ARCHITECTURE.md` §3) must have meaningfully different UX, not a shared screen with a flag.

---

## 8. UI/UX Standard

Every screen must have: loading state, empty state (where applicable), error state, retry behavior (where applicable), meaningful feedback, appropriate navigation, responsive layout.

Use: attractive typography, visual hierarchy, destination imagery, meaningful icons, subtle animation, micro-interactions, polished cards, appropriate spacing, smooth transitions. Avoid unnecessary visual clutter.

---

## 9. Testing Requirement

Every phase must include tests. Before declaring a phase complete:

1. Run unit tests.
2. Run integration tests.
3. Run relevant API tests.
4. Run type checking.
5. Run linting.
6. Run the application.
7. Test the actual user flow.
8. Fix discovered errors.
9. Repeat until stable.

**Do not report tests as passing unless they were actually executed.**

---

## 10. Completion Report

At the end of every phase, create/update `docs/PHASE_STATUS.md` with:

- phase name
- objective
- requirements implemented
- files created
- files modified
- database changes
- API changes
- UI changes
- external integrations
- tests executed
- test results
- known limitations
- unresolved issues
- environment variables required
- next phase dependencies

Every item classified as one of: **COMPLETE / PARTIAL / BLOCKED / NOT IMPLEMENTED**.

**Never describe PARTIAL as COMPLETE.**

---

## 11. Phase Control

Implement only the requested phase. Do not automatically start the next phase.

At the end of a phase: **STOP.** Wait for explicit authorization to continue.

---

## 12. Product Quality Standard

The evaluator must be able to use the application as a real product. The final system supports:

```
Authentication → Personalization → Trip Creation → AI Planning → Conversational Refinement
→ Maps → Location Awareness → Heritage Guidance → Visual Q&A → Language Assistance
→ Live Speech Translation → Memory Box → Reviews → Collections → Hotel/Flight integration
→ Notifications → Persistent Data → Secure Authentication → Production Deployment
```

Where a third-party commercial service cannot reasonably be fully activated (e.g. no live booking-partner agreement, no production SMS account), the system must provide the most complete legitimate integration possible and clearly document the remaining dependency in `PHASE_STATUS.md`.

**Never fabricate successful bookings, payments, availability, or external transactions.**

---

## 13. Known Open Items Governing Early Phases

Per `ARCHITECTURE_REVIEW.md`, the following must be resolved as part of (not after) the phase that first touches the affected area — not deferred silently:

- **C1/C2 (CRITICAL):** `profiles.pace` column and `audit_logs.actor_user_id` ON DELETE behavior must be fixed in the Phase-1 schema migration, before onboarding/auth is built.
- **H1:** Auth/profile-provisioning mechanism (DB trigger vs. API endpoint) must be resolved to one mechanism before Phase 1 auth work starts.
- **H3:** Caching/rate-limit/idempotency backing store (Redis, or an explicit documented single-instance constraint) must be decided before any endpoint depending on rate limiting or idempotency keys is built.
- **H4:** Admin content-tooling decision (even "use FastAPI `/docs` for MVP") must be made before heritage-content curation work starts.
- **H6:** Memory-box/expense/notes RLS tightening must land before Phase 2 group-trip features ship.
- **H7:** The §16 weather business rule must be added to the itinerary generation validator when F3 is implemented.

This list is not exhaustive — consult `ARCHITECTURE_REVIEW.md` directly for the full 35-item audit before starting any phase it overlaps with.
