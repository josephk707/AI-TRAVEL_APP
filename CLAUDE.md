# AI Personalized Tourist Guide (TC-SO1) — Permanent Project Development Rules

This file governs all engineering work on this repository. It is binding for every session and every phase, not advisory.

---

## 1. Source of Truth Hierarchy

- **`docs/AI_Tourist_Guide_Master_PRD_SDLC.pdf` is the product source of truth.** It defines business requirements, functional requirements, business rules, scope, and product intent. When any question of *what the product should do* arises, this document wins.
- **The seven engineering documents are the implementation references** and are authoritative for *how* the product is built, unless an explicit, documented architecture decision overrides them:
  - `docs/IMPLEMENTATION_BLUEPRINT.md` — feature-by-feature plan, phase roadmap
  - `docs/DATABASE_SCHEMA.md` — schema, relationships, Row Level Security, migrations
  - `docs/API_SPECIFICATION.md` — endpoint contracts, error model
  - `docs/AI_ARCHITECTURE.md` — AI/RAG pipelines, provider abstraction
  - `docs/MOBILE_ARCHITECTURE.md` — client architecture, navigation, UX modes
  - `docs/DEPLOYMENT_PLAN.md` — environments, CI/CD, ops
  - `docs/TESTING_PLAN.md` — test strategy per layer
- `docs/ARCHITECTURE_REVIEW.md` records open findings against the above — check it before touching an area it flags, and do not reintroduce an issue it already documents.
- `docs/PHASE_STATUS.md` is the living record of what has actually been built, phase by phase — read it to know true current state before assuming any feature exists.
- All of the above must be read — at minimum the sections relevant to the feature at hand — before implementing any major feature. Do not implement from memory or assumption when a document answers the question.

---

## 2. Engineering Objective

This is a complete, production-oriented application. It is explicitly **not** a prototype, a static UI, a mockup, a proof of concept, a collection of disconnected screens, or a hardcoded demo.

A feature is not complete until its full path works end-to-end:

```
USER INTERFACE → API → BUSINESS LOGIC → DATABASE / EXTERNAL SERVICE → RESPONSE → USER INTERFACE
```

---

## 3. No Dummy or Fake Functionality

- Never fake functionality. Every implemented feature must be genuinely functional.
- Never replace required persistence with localStorage, in-memory arrays, or any non-durable store standing in for the database.
- Never create a button, action, or UI affordance that claims to perform an operation unless that operation actually works end-to-end.
- Never claim an external API integration works without having actually tested it against the real service.
- Never claim AI functionality works if the response is hardcoded, templated-as-if-dynamic, or stubbed.
- Never fabricate successful bookings, payments, availability, or any external transaction. Where a third-party commercial service cannot reasonably be fully activated (no live partner agreement, no production account, etc.), implement the most complete legitimate integration possible and clearly document the remaining dependency in `PHASE_STATUS.md` — do not simulate success.

---

## 4. Credentials & Secrets

- Never hardcode credentials, API keys, tokens, or secrets anywhere in source code.
- Never expose secrets in frontend/mobile source code — only publishable/anon-scoped keys belong in the client; server-side secrets stay server-side.
- Never commit API keys, `.env` files with real values, or credentials to version control.
- Secrets are read from environment variables / the platform's secret store, per `DEPLOYMENT_PLAN.md` §4.

---

## 5. Secure Authentication

- Authentication follows `IMPLEMENTATION_BLUEPRINT.md` §1.3 and `DATABASE_SCHEMA.md` §2: Google OAuth2 via Supabase Auth, no first-party password storage.
- Never trust a client-provided user ID when identity can be derived from the authenticated session/token. Every server-side operation identifies the acting user from the verified auth token, never from a request body field.
- Enforce authorization server-side, on every request — client-side checks are UX convenience only, never a security boundary.
- Respect and correctly implement database Row Level Security as defined in `DATABASE_SCHEMA.md` — RLS is defense-in-depth, not a substitute for server-side authorization, and server-side authorization is not a substitute for RLS. Both layers must be correct.

---

## 6. Real Database Persistence

- All persistent business data lives in the database — no silent fallback to local/in-memory/client-only state for anything the product requires to survive a session or be shared across devices.
- Use migrations for every schema change. Never modify a deployed schema manually without a corresponding migration file.
- Use foreign keys, appropriate indexes, and constraints — not application-layer-only integrity checks for relationships the database can enforce directly.
- Use Row Level Security and explicit user ownership on every user-scoped table.
- Every schema change must be documented — update `DATABASE_SCHEMA.md` alongside the migration, not after the fact or not at all.

---

## 7. Proper API Architecture

Every API endpoint must:
- validate input
- authenticate where required
- authorize access
- return predictable, documented response shapes
- return appropriate HTTP status codes and a structured error envelope (`API_SPECIFICATION.md` §1)
- handle external-dependency failures gracefully (degrade, don't crash)
- have tests

Business logic belongs in service/business-logic layers, not in route handlers — route handlers parse/validate the request, call a service, and shape the response.

---

## 8. AI Provider Abstraction

- AI is a core product capability, not a bolt-on — treat it with the same engineering rigor as any other critical system.
- AI must be implemented through a proper service abstraction (`LLMGateway`, per `AI_ARCHITECTURE.md` §1). Never scatter direct LLM/vendor SDK calls throughout the application — every call site goes through the gateway interface, so the provider is a config choice, not a hardcoded dependency.
- Use structured outputs for AI responses where appropriate, and validate model responses (and any AI structured output) before persisting or returning them to the client — never trust a model response blindly.
- Use grounded retrieval (RAG) for factual heritage information. Never present unsupported, ungrounded generated historical claims as verified fact — low-confidence output must be visibly flagged, not smoothed over.
- AI calls must receive only the context necessary for the task — no indiscriminate context dumping.
- User-specific information must be isolated by authenticated user — no cross-user context leakage into a prompt, cache key, or retrieval scope.

---

## 9. Proper Error Handling

- Never silently swallow errors. Every failure path either recovers with a documented fallback or surfaces the failure explicitly (to logs, to the user, or both, per the specific feature's documented error-handling behavior).
- Handle loading, success, empty, and error states explicitly in every screen and every API consumer — no undefined/blank behavior for any of these states.
- External API and AI-provider failures degrade gracefully per `API_SPECIFICATION.md` §1 and `AI_ARCHITECTURE.md` — never a hard crash because a third-party dependency is unavailable.

---

## 10. Testing Requirements

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

**Do not report tests as passing unless they were actually executed.** Tooling and coverage expectations per layer are defined in `TESTING_PLAN.md`.

---

## 11. UI/UX Quality Requirements

The mobile application must be responsive, accessible, visually polished, intuitive, performant, and production-oriented — it should feel like a premium travel application, not a generic dashboard. Planning Mode and On-Trip Mode (`MOBILE_ARCHITECTURE.md` §3) must have meaningfully different UX, not a shared screen behind a flag.

Every screen must have: loading state, empty state (where applicable), error state, retry behavior (where applicable), meaningful feedback, appropriate navigation, and a responsive layout.

Use attractive typography, clear visual hierarchy, destination imagery, meaningful icons, subtle animation, micro-interactions, polished cards, appropriate spacing, and smooth transitions. Avoid unnecessary visual clutter.

---

## 12. Phase-Based Development

- Implement only the phase explicitly requested. Do not build ahead of the current phase and do not implement future-phase functionality in a way that destabilizes the MVP.
- Do not introduce microservices unless justified by the architecture documents.
- Prefer maintainability over unnecessary complexity in every implementation decision.

### Explicit prohibition — do not automatically start the next phase

At the end of a phase: **STOP.** Update `docs/PHASE_STATUS.md` and wait for explicit authorization before beginning the next phase. Never chain into subsequent phases on your own initiative, regardless of how complete or stable the current phase appears.

---

## 13. Documentation Requirements

- Never silently change product requirements. Never silently change architecture. If a change to either is genuinely necessary, document the decision explicitly (what changed, why, where) rather than making it quietly.
- If the PRD or a derived engineering document is ambiguous, identify the ambiguity explicitly and document the decision made to resolve it — do not guess silently and move on.
- Every schema change is documented in `DATABASE_SCHEMA.md`. Every architecture deviation is documented in the relevant engineering document or `PHASE_STATUS.md`.

---

## 14. Completion Criteria

At the end of every phase, create or update `docs/PHASE_STATUS.md` with:

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

Classify every item as one of: **COMPLETE / PARTIAL / BLOCKED / NOT IMPLEMENTED**.

**Never describe PARTIAL as COMPLETE.**

The evaluator must be able to use the application as a real product. A phase is not "done" because code was written for it — it is done when the full path (UI → API → business logic → database/external service → response → UI) has been run and verified, per §10 above.
