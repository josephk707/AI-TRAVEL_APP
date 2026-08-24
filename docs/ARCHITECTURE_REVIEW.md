# Architecture Review
## Consistency & Feasibility Audit — AI Personalized Tourist Guide (TC-SO1)

| | |
|---|---|
| Scope | `IMPLEMENTATION_BLUEPRINT.md`, `DATABASE_SCHEMA.md`, `API_SPECIFICATION.md`, `AI_ARCHITECTURE.md`, `MOBILE_ARCHITECTURE.md`, `DEPLOYMENT_PLAN.md`, `TESTING_PLAN.md` |
| Compared against | `docs/AI_Tourist_Guide_Master_PRD_SDLC.pdf` (Master PRD & SDLC, v1.0, 21-Aug-2026) |
| Status | **Audit complete. Implementation should not begin until CRITICAL and HIGH items below are resolved by the product/engineering owner.** |
| Note on method | This review re-read all seven documents from disk in full and cross-checked every table, endpoint, and pipeline step named in one document against its counterpart in the others and against the PRD text. No architecture was changed while performing this review. |

---

## 0. Executive Summary

35 findings: **2 CRITICAL, 7 HIGH, 15 MEDIUM, 11 LOW.**

The overall shape of the architecture is sound and traceable to the PRD — every MVP module has a feature entry, every feature entry has a plausible DB/API/AI mapping, and the phase boundaries (MVP → Phase 2 → Phase 3 → Phase 4) are respected almost everywhere. The problems found are concentrated in three places:

1. **Two CRITICAL data-modeling defects** that would silently break a Must-priority requirement if implemented as currently documented: a missing `pace` column (onboarding data loss) and a foreign key that would block the account-deletion workflow.
2. **Cross-document contradictions** — places where `IMPLEMENTATION_BLUEPRINT.md`, `API_SPECIFICATION.md`, `DATABASE_SCHEMA.md`, and `AI_ARCHITECTURE.md` each describe the same mechanism differently (auth/profile provisioning; the Dynamic Re-Adaptation endpoints). These are genuine authoring errors introduced across the seven documents, not PRD ambiguity.
3. **One silently dropped piece of the PRD's own recommended stack** (the Caching/Redis row of §26.4) that several other decisions (rate limiting, idempotency keys, response caching) quietly depend on without ever being reconciled — this is exactly the kind of undisclosed architecture change the instructions asked to avoid, and it is called out plainly in §8 below.

Nothing found here requires re-architecting the system. Every fix is additive (a column, a table, an endpoint, a tightened RLS policy, an explicit decision recorded) rather than a redesign.

---

## 1. Findings Index

| ID | Severity | Area | One-line summary |
|---|---|---|---|
| C1 | CRITICAL | Database | `profiles` has no `pace` column — FR-003's explicit onboarding input is silently dropped |
| C2 | CRITICAL | Database | `audit_logs.actor_user_id` has no `ON DELETE SET NULL` — blocks the account-deletion workflow it's supposed to support |
| H1 | HIGH | Cross-doc | Three documents disagree on what actually creates the `profiles` row (DB trigger vs. API endpoint) |
| H2 | HIGH | API ↔ Blueprint | `disruption_events` (FR-014) has two different, contradictory API surfaces across two documents |
| H3 | HIGH | Architecture | Redis/caching (PRD §26.4's own Recommended row) is silently absent despite being functionally required elsewhere |
| H4 | HIGH | Ops/Content | No admin tool is specified anywhere for curating heritage content — the MVP's most distinctive feature has no content pathway |
| H5 | HIGH | Auth model | "Edit rights" language in the Blueprint has no PRD basis and no RLS implementation |
| H6 | HIGH | RLS/Privacy | Any group-trip member can read, modify, or **delete** another member's memory-box photos, notes, and expenses |
| H7 | HIGH | AI pipeline | The §16 weather business rule (Must, MVP-tagged) is missing from the itinerary generation pipeline's validation steps |
| M1 | MEDIUM | Blueprint | "Business logic" is not a distinct column in the per-feature table, despite being explicitly requested |
| M2 | MEDIUM | Database | Six foreign keys have no explicit `ON DELETE` behavior |
| M3 | MEDIUM | API ↔ Database | Idempotency-Key mechanism has no backing store defined anywhere |
| M4 | MEDIUM | Database | PostGIS adds real technology surface for a lean team beyond the PRD's literal stack |
| M5 | MEDIUM | Testing | Testcontainers needs a custom Postgres+pgvector+PostGIS image; not addressed |
| M6 | MEDIUM | Testing/Deploy | Full CI/testing rigor assumed affordable from day one for a small/student team |
| M7 | MEDIUM | Deploy/AI | No separation of LLM API keys/cost budget between staging and production |
| M8 | MEDIUM | AI ↔ Database | `ai_messages.conversation_id` is `NOT NULL` but Visual Q&A is a non-conversational endpoint |
| M9 | MEDIUM | Mobile | No screen/flow for account-deletion request (§27 Must requirement) |
| M10 | MEDIUM | Mobile | No `POIDetailScreen` — PRD's explicit "Reviews (view and submit)" Key Screen has no home |
| M11 | MEDIUM | API | Dynamic/arbitrary text translation (FR-009 Phase 2) has no endpoint — only speech translation was built |
| M12 | MEDIUM | Dependencies | SMS/Email provider for SOS is a new, un-budgeted external dependency not in the PRD's integration list |
| M13 | MEDIUM | API | "Data export" actions aren't wired to `audit_logs` writes despite §27 requiring it |
| M14 | MEDIUM | Deploy | No scheduled heritage-content freshness/accuracy review cadence, despite §36 requiring one |
| M15 | MEDIUM | Feasibility | Phase-1 scope size has no effort/timeline estimate to sanity-check against team size |
| L1 | LOW | Docs | `/v1/` prefix notation inconsistent between Blueprint and API spec |
| L2 | LOW | Docs | Path-parameter naming (`{id}` vs `{poi_id}`) inconsistent between Blueprint and API spec |
| L3 | LOW | Database | Mermaid ERD omits several real (correctly-defined) tables |
| L4 | LOW | AI | Two concrete LLM adapters implied for MVP; only one is needed at launch |
| L5 | LOW | Deploy | Analytics rollup job may be premature before real usage volume exists |
| L6 | LOW | Blueprint | F15's "planning-time" label undersells that it also ships expense tracking |
| L7 | LOW | Blueprint | Modules 11/12 (Attractions, Restaurants) have no dedicated F-number |
| L8 | LOW | PRD gap | Persona-level "accessibility-aware suggestions" never became a formal requirement or schema field |
| L9 | LOW | RLS | Raw heritage embeddings are directly client-readable, bypassing narration orchestration |
| L10 | LOW | RLS | No policy lets a trip member read a co-member's public profile fields |
| L11 | LOW | RLS | Admin UPDATE/DELETE policies missing for `pois`/`heritage_content` (INSERT-only exists) |

---

## 2. Item-by-Item Audit

### 2.1 Does every MVP requirement have a corresponding implementation plan?

**Verdict: Yes, with one labeling nitpick (L6).** Every bullet in PRD §29.1 (MVP definition) maps to a numbered feature (F1–F18) in `IMPLEMENTATION_BLUEPRINT.md` §3. Two items not explicitly bulleted in §29.1 (Visual Q&A, Post-Trip Feedback) were deliberately pulled into Phase 1 with an explicit, cited resolution note rather than silently added — see §6 (Assumptions Log) items A1–A2. No MVP requirement was found unimplemented.

---

### 2.2 Does every planned feature have all required dimensions (frontend, backend API, business logic, database, auth, external API, error handling, testing)?

**Verdict: Mostly, with one structural gap (M1) and several downstream completeness gaps (H2, M8–M11) surfaced below.**

#### M1 — MEDIUM — "Business logic" is not a distinct dimension in the Blueprint

- **Problem:** The audit explicitly asked to verify each feature has a *business logic* dimension separate from its backend API. `IMPLEMENTATION_BLUEPRINT.md`'s per-feature table (§3–§6) uses 10 columns (frontend, backend API, database tables, external API, AI component, auth/authz, error handling, testing, dependencies, priority) — there is no dedicated "business logic" column. Business-rule ownership is described narratively, split across the "error handling" cell and `AI_ARCHITECTURE.md`'s prose (e.g. §2 step 4: "Business-rule validation... NOT delegated to the LLM").
- **Source PRD section:** §16 (Business Rules), §14 (each FR's own "Business Rules" row).
- **Current implementation decision:** Business logic is treated as an implicit property of the backend API and AI pipeline rather than an explicit, auditable column.
- **Why it is a problem:** It works today because a human (me) tracked every §16 rule down manually while writing this review. A future engineer skimming `IMPLEMENTATION_BLUEPRINT.md` feature-by-feature has no single column to check "what business rule governs this feature and where is it enforced" — which is exactly how H7 (a missing business rule) went unnoticed until this audit.
- **Recommended resolution:** Add an explicit "Business Logic / Rules Enforced" column to the Blueprint's per-feature tables before implementation starts, citing the exact §16/FR-level rule and which layer enforces it (validator function, DB constraint, or RLS policy).

---

### 2.3 Database relationships and foreign keys

**Verdict: The schema is relationally sound overall, but one FK gap (C2) breaks a documented workflow, and six more (M2) rely on undocumented default behavior.**

#### C2 — CRITICAL — `audit_logs.actor_user_id` will block the account-deletion workflow it exists to support

- **Problem:** `audit_logs.actor_user_id uuid references public.profiles(id)` has **no `ON DELETE` clause**, so Postgres defaults to `NO ACTION`. `DEPLOYMENT_PLAN.md` §6 (Data Deletion Workflow) states: *"profiles row and all owned data cascades per FK `on delete cascade`."* But §27 also requires *"sensitive actions (data export, account deletion, admin content edits) are logged for accountability"* — meaning any user who has ever exported their memory box (a routine, non-admin action any traveller can take, per `API_SPECIFICATION.md` §10) will have an `audit_logs` row with `actor_user_id` pointing at them. When that user later requests account deletion, the cascade from `profiles` will hit this FK, Postgres will refuse the delete (`actor_user_id` has no path to resolve), and the entire deletion transaction will fail.
- **Source PRD section:** §27 ("Data deletion: users can request account and data deletion" — Must, All stakeholders) and §27 ("Audit logging: sensitive actions... are logged").
- **Current implementation decision:** `audit_logs.actor_user_id` left with default (implicit) `NO ACTION` FK behavior; `analytics_events.user_id` was correctly given `on delete set null` in the same document, but this column was not.
- **Why it is a problem:** This is not a hypothetical edge case — any traveller who exports their trip photos before deleting their account (an entirely plausible, even expected, sequence of actions) will hit a documented feature that cannot actually complete as specified. It directly breaks a Must-priority, trust-critical requirement.
- **Recommended resolution:** Change to `actor_user_id uuid references public.profiles(id) on delete set null` — the audit trail should survive the actor's account deletion (this is standard practice for audit logs and doesn't weaken accountability, since the row still records *what* happened and *when*, only losing the ability to join back to a now-deleted account).

#### M2 — MEDIUM — Six foreign keys have no explicit `ON DELETE` behavior

- **Problem:** `itinerary_items.poi_id`, `quick_plan_items.poi_id`, `reviews.trip_id`, `sos_events.trip_id`, `profile_interests.interest_id`, and `reviews.moderated_by` are all declared without an `ON DELETE` clause, defaulting to `NO ACTION`/`RESTRICT`.
- **Source PRD section:** No direct PRD citation — this is a schema-completeness gap surfaced by the review's own instruction to "check all database relationships and foreign keys."
- **Current implementation decision:** Implicit default FK behavior.
- **Why it is a problem:** In practice this means an admin can never delete a `pois` row that has ever appeared in any itinerary or quick plan, and a review can silently outlive the trip that justified it existing — not necessarily wrong, but currently **undecided** rather than **decided**. (`reviews.trip_id` and `sos_events.trip_id` are lower risk in practice because the co-referencing `user_id`/`owner_id` FK on the same row already has `on delete cascade`, so the profile-deletion cascade path resolves those two before conflict — but this was verified by hand-tracing the cascade graph, not by an explicit policy, which is fragile.)
- **Recommended resolution:** Decide and declare explicitly per column: `itinerary_items.poi_id → on delete set null` (column is nullable; a deleted POI shouldn't delete the itinerary item, just orphan the reference for `verify_on_arrival`-style handling), `quick_plan_items.poi_id → on delete cascade` (quick plans are low-stakes, ephemeral), `reviews.trip_id → on delete cascade`, `sos_events.trip_id → on delete cascade`, `profile_interests.interest_id → on delete cascade`, `reviews.moderated_by → on delete set null`.

#### L3 — LOW — Mermaid ERD omits several real tables

- **Problem:** The entity-relationship diagram in `DATABASE_SCHEMA.md` §14 omits `profile_interests`, `phrasebook_entries`, `device_push_tokens`, `sos_events`, `weather_cache`, `audit_logs`, `analytics_events`, `bookings`, and `trip_recaps` — all of which exist correctly in the DDL above it.
- **Source PRD section:** N/A (documentation completeness only).
- **Current implementation decision:** Diagram was scoped to the "core narrative" relationships rather than every table.
- **Why it is a problem:** A reader using the diagram as their primary mental model will believe fewer tables exist than actually do; purely cosmetic, no schema defect.
- **Recommended resolution:** Either expand the diagram to full coverage or add a one-line note under it stating which tables are intentionally omitted and why.

---

### 2.4 Row Level Security — can users access ONLY their own private data?

**Verdict: No, not fully.** Most tables are correctly scoped (favorites, collections, notifications, trusted_contacts, location_pings, feedback_signals, ai_conversations all correctly restrict to `auth.uid()`). But the `is_trip_member()` helper is used as a blanket "any member can do anything" policy on tables where per-author ownership plausibly matters more than trip membership, and one authorization concept referenced in the Blueprint has no RLS backing at all.

#### H5 — HIGH — "Edit rights" language has no PRD basis and no RLS implementation

- **Problem:** `IMPLEMENTATION_BLUEPRINT.md` F5 (Conversational Itinerary Modification) states: *"Auth/authz | Trip owner or trip member with edit rights (group trips, Phase 2)"* — implying a permission tier beyond simple membership. But (a) the PRD's FR-012 never defines a role/permission concept distinct from "organiser" vs. "member," and (b) `DATABASE_SCHEMA.md`'s actual RLS policy (`itinerary_items_member`, via `is_trip_member()`) grants full read/write to **any** trip member regardless of role — there is no "edit rights" flag or check anywhere in the schema.
- **Source PRD section:** FR-012 (§14), Module 16 (§12).
- **Current implementation decision:** Blueprint prose implies a permission model the database does not implement.
- **Why it is a problem:** This is a genuine ambiguity I introduced and then failed to resolve consistently — the phrase "with edit rights" was added without PRD support and never followed through into the schema, leaving a real question (should all group members be able to edit the shared itinerary, or only some?) implicitly answered two different ways in two different documents.
- **Recommended resolution:** Before Phase 2 implementation, explicitly decide: either (a) drop "edit rights" from the Blueprint and document that any accepted member can propose/apply itinerary changes (matching the current permissive RLS and FR-012's plain reading — "members view the shared plan and can propose changes visible to the group"), or (b) if differentiated permissions are actually wanted, design a role/permission column and a corresponding RLS predicate. This is Phase 2 scope, not MVP-blocking, but should not carry an unresolved contradiction into Phase 2 planning.

#### H6 — HIGH — Any group-trip member can delete another member's memory-box photos, notes, and expenses

- **Problem:** `memory_items_member`, `budget_expenses_member`, and `trip_raw_notes_member` are all `for all using (is_trip_member(trip_id))` policies — meaning any accepted member of a group trip has full **SELECT, INSERT, UPDATE, and DELETE** rights over every other member's rows in these tables, not just their own. In practice, this means Member B can delete Member A's uploaded photos from the shared Memory Box.
- **Source PRD section:** §11 ("Trip memory box for photos and notes" — framed as personal), §23 ("Photo/memory data: User-uploaded trip photos and notes"), §43.3 (the product's own stated bar: "never surprise the user with unannounced data loss").
- **Current implementation decision:** Trip-membership alone was used as the authorization boundary for these three tables, the same pattern used correctly for genuinely shared/collaborative data (`itinerary_items`, `disruption_events`, where FR-012 explicitly wants shared edit access).
- **Why it is a problem:** The PRD never explicitly addresses per-member privacy within a group trip's memory box, but §43.3's explicit promise — memory-box items are never deleted without the owner's knowledge — is directly undermined if a co-traveller can delete them outright with no consent or notification. This is the clearest instance found of the audit's own item-4 question ("do users access only their own private data?") being answered "no."
- **Recommended resolution:** Split the single "for all" policy per table into a permissive SELECT (any trip member, since shared *viewing* is clearly intended — "gallery" framing throughout `MOBILE_ARCHITECTURE.md`) plus a restrictive INSERT/UPDATE/DELETE scoped to `user_id = auth.uid()` (the uploader/author) or the trip owner. Apply the same split to `budget_expenses` and `trip_raw_notes` unless a product decision explicitly wants shared-edit for those (arguably defensible for a jointly-managed trip budget, less so for someone else's uploaded photo).

#### L9 — LOW — Raw heritage embeddings are directly client-readable

- **Problem:** `heritage_embeddings_read` grants any authenticated user `SELECT` on `heritage_content_embeddings`, including raw `chunk_text` — bypassing the narration API's layer/section gating and confidence-flagging entirely if read directly via the Supabase client rather than through `GET /heritage/{poi_id}/narration`.
- **Source PRD section:** Not a private-data concern (heritage content is public catalog data, §22), so this doesn't violate item 4's core privacy question, but it is broader access than necessary.
- **Current implementation decision:** Open read policy for simplicity.
- **Why it is a problem:** No legitimate client use case needs raw embedding vectors or unformatted chunk text; the API is the intended access path.
- **Recommended resolution:** Restrict this table's RLS to service-role-only reads (remove the client SELECT policy); the narration endpoint already serves everything a client should see.

#### L10 — LOW — No policy lets a trip member read a co-member's public profile fields

- **Problem:** `profiles_select_own` only allows `auth.uid() = id` (or admin). A future direct-client read (e.g. Supabase Realtime for live group-trip UI) showing "who's in this trip" would return nothing for co-members' `display_name`/`avatar_url`.
- **Source PRD section:** FR-012 (group trips need to show member identity for invites/preferences).
- **Current implementation decision:** Profile visibility not extended to trip co-members.
- **Why it is a problem:** Masked today because all reads are backend-mediated via the service-role key (per the two-layer model), but it's a latent gap if any direct-client read path is ever added for group-trip UI.
- **Recommended resolution:** Add a policy allowing `SELECT` of `display_name`/`avatar_url` (not the full row) to any user sharing a `trip_members` row, or document explicitly that group-trip member display is permanently backend-mediated.

#### L11 — LOW — Admin UPDATE/DELETE RLS policies missing for `pois`/`heritage_content`

- **Problem:** `pois_write_admin` and `heritage_content_write_admin` are `INSERT`-only policies; no admin `UPDATE`/`DELETE` policy exists for either table.
- **Source PRD section:** §26.2 (role-based access for "internal/admin for content and moderation tooling").
- **Current implementation decision:** Only insert covered.
- **Why it is a problem:** Masked today by service-role bypass in the `/admin/*` FastAPI routes, but incomplete as defense-in-depth.
- **Recommended resolution:** Add matching admin `UPDATE`/`DELETE` policies for consistency and to actually satisfy the "defense-in-depth" rationale stated in `DATABASE_SCHEMA.md` §2.

---

### 2.5 Does the API specification match the database schema?

**Verdict: Mostly, with three concrete gaps.**

#### C1 — CRITICAL — `profiles` has no `pace` column; onboarding data is silently dropped

- **Problem:** `API_SPECIFICATION.md` §3 documents `POST /onboarding/responses` accepting `{"interest_ids": [...], "travel_style": "...", "budget_bracket": "...", "pace": "relaxed"}`, and `IMPLEMENTATION_BLUEPRINT.md` F2 explicitly lists "pace" as one of the captured onboarding screens. But `DATABASE_SCHEMA.md`'s `profiles` table has columns for `travel_style` and `budget_bracket` — **there is no `pace` column anywhere in the schema.**
- **Source PRD section:** FR-003 (§14): *"Inputs: Selected interests, travel style, **pace**, rough budget bracket."* Also tied to the Family Traveller persona's explicit need for "Pace-aware scheduling" (§9).
- **Current implementation decision:** The API and Blueprint both correctly capture "pace" as a required input; the database schema simply omits the column.
- **Why it is a problem:** This is a Must-priority (BR-019), Phase-1 requirement with an explicit PRD-named input field. As specified, the backend would accept `pace` from every user at onboarding and have nowhere to persist it — silent, permanent data loss of a field the PRD calls out by name, undermining a persona-critical personalization signal for the life of the product until someone happens to notice.
- **Recommended resolution:** Add `pace text` (e.g. `check (pace in ('relaxed','balanced','packed'))`) to the `profiles` table before any implementation begins.

#### H2 — HIGH — `disruption_events` (FR-014) has two contradictory API surfaces

- **Problem:** `IMPLEMENTATION_BLUEPRINT.md` F20 states the backend API is `GET /v1/trips/{trip_id}/disruptions` and `POST /v1/trips/{trip_id}/disruptions/{id}/resolve`. But `API_SPECIFICATION.md` has **no such endpoints anywhere** — its own traceability table (§21) states instead: *"FR-014 | (server-initiated) `disruption_events` surfaced via `GET /notifications` + `POST /trips/{id}/itinerary/modify` accept flow."* These are two different, incompatible designs for the same Phase-2 feature, and neither document reconciles with the other.
- **Source PRD section:** FR-014 (§14): *"User confirms, edits, or dismisses the proposal — nothing changes automatically without confirmation."*
- **Current implementation decision:** Undecided — the two authoritative documents disagree.
- **Why it is a problem:** FR-014 requires a concrete accept/dismiss action per proposal. "Surfaced via notifications" alone doesn't specify how a user's accept/dismiss decision is actually submitted back to the server — the API spec's own described mechanism is under-specified, and the Blueprint's alternative (dedicated `/disruptions` endpoints) was never added to the API spec. An engineer building Phase 2 from these documents cannot tell which contract to implement.
- **Recommended resolution:** Reconcile before Phase 2 begins — recommend keeping the Blueprint's dedicated `GET /trips/{trip_id}/disruptions` + `POST .../disruptions/{id}/resolve` endpoints (cleaner, directly maps to the `disruption_events` table and its `status` enum) and adding them to `API_SPECIFICATION.md` formally, retiring the vaguer "via notifications" description in its traceability table.

#### M3 — MEDIUM — Idempotency-Key mechanism has no backing store

- **Problem:** `API_SPECIFICATION.md` §1 states: *"the server stores the key→response mapping for 24h"* for every `POST` endpoint. No table for this exists in `DATABASE_SCHEMA.md`, and no cache/store is named in `DEPLOYMENT_PLAN.md`.
- **Source PRD section:** §15 (NFR — Data Integrity: "idempotent write operations on all mutating endpoints").
- **Current implementation decision:** Referenced functionally, never given a concrete storage mechanism.
- **Why it is a problem:** Without a defined store, this NFR cannot actually be implemented as documented — and if implemented ad hoc (e.g., in-process memory) on a horizontally-scaled backend, it will silently fail to dedupe requests routed to a different instance. Directly related to H3 below.
- **Recommended resolution:** Add an explicit `idempotency_keys` table (or Redis-backed store, once H3 is resolved) with `(key, user_id, endpoint, response_body, created_at)` and a TTL/cleanup job.

#### M8 — MEDIUM — `ai_messages.conversation_id` is `NOT NULL` but Visual Q&A is not a conversation

- **Problem:** `DATABASE_SCHEMA.md` requires every `ai_messages` row to reference an `ai_conversations` row. `AI_ARCHITECTURE.md` §6 (Visual Q&A Pipeline) says the response is "logged to `ai_messages`," but Visual Q&A (`POST /heritage/{poi_id}/photo-qa`) is a single-shot endpoint, not part of an ongoing chat thread the way `POST /trips/{id}/itinerary/modify` is.
- **Source PRD section:** FR-008 (§14) — no PRD requirement that Visual Q&A be conversation-threaded.
- **Current implementation decision:** Schema forces a conversation association; pipeline doesn't say how one is obtained.
- **Why it is a problem:** As written, implementing the Visual Q&A logging step requires either (a) silently creating a throwaway one-message `ai_conversations` row per photo question (workable, but never stated), or (b) the implementation will hit a `NOT NULL` constraint violation and simply fail to log — which would quietly break the golden-set/audit trail this exact logging exists to support (`AI_ARCHITECTURE.md` §6 step 5, §11).
- **Recommended resolution:** Either make `ai_messages.conversation_id` nullable and add a `context_type` discriminator (`chat` | `photo_qa`), or explicitly document that Visual Q&A creates a single-message conversation per call — pick one and state it.

---

### 2.6 Does the AI architecture match the APIs and database?

**Verdict: Mostly, with the missing weather rule (H7) and the conversation-id gap (M8, above) as the two concrete defects.**

#### H7 — HIGH — The §16 weather business rule is missing from the itinerary generation pipeline

- **Problem:** PRD §16 states as a Business Rule: *"Weather: outdoor activities affected by adverse forecast weather are flagged with a suggested indoor or alternative option."* Module 14 ("Weather Intelligence: Forecast-aware planning **and re-adaptation**") is tagged **MVP** phase in PRD §12's module table — meaning this rule should apply at *generation* time (Phase 1), not only at re-adaptation time (Phase 2, F20). But `AI_ARCHITECTURE.md` §2 step 4 ("Business-rule validation") lists only four checks — budget tolerance, opening-hours conflicts, travel-time buffers, and item overlap. The weather-flagging rule is not among them, even though F3's own Blueprint row already lists the Weather API as an external dependency for "outdoor-activity flagging."
- **Source PRD section:** §16 (Business Rules), Module 14 (§12).
- **Current implementation decision:** Weather API is wired in as a data source but the actual business rule it exists to support was never added to the validator's explicit step list.
- **Why it is a problem:** This is a Must-priority, MVP-tagged rule that an engineer implementing strictly from `AI_ARCHITECTURE.md`'s pipeline description (rather than re-deriving it from PRD §16 independently) would miss entirely.
- **Recommended resolution:** Add a fifth validation step to `AI_ARCHITECTURE.md` §2 step 4: "outdoor-category itinerary items checked against `weather_cache` forecast for the relevant date; adverse-weather items flagged with a suggested indoor/alternative swap from the candidate POI set."

---

### 2.7 Does the mobile architecture match the API specification?

**Verdict: Mostly consistent for flows it covers, but two PRD-required screens are missing from the navigation tree.**

#### M9 — MEDIUM — No mobile screen for account-deletion request

- **Problem:** `API_SPECIFICATION.md` §2 defines `POST /auth/account/delete-request`, and `DEPLOYMENT_PLAN.md` §6 documents the full backend workflow. But `MOBILE_ARCHITECTURE.md`'s navigation structure (§2) has no corresponding screen or entry point anywhere (not even implied under `ProfileScreen`/`PreferencesScreen`).
- **Source PRD section:** §27 (Must, All stakeholders: "users can request account and data deletion").
- **Current implementation decision:** Backend-only; no client-side UI planned.
- **Why it is a problem:** A backend endpoint a user can never actually reach from the app doesn't satisfy the requirement.
- **Recommended resolution:** Add an explicit "Delete my account" action under `PreferencesScreen` (with the confirmation friction appropriate to a destructive, hard-to-reverse action) to the navigation structure.

#### M10 — MEDIUM — No `POIDetailScreen` — PRD's "Reviews" Key Screen has no home

- **Problem:** PRD §25.1 lists "Reviews (view and submit)" as one of its explicit Key Screens. `IMPLEMENTATION_BLUEPRINT.md` F14 references a "POI detail screen" narratively ("Review list on POI detail screen"), but `MOBILE_ARCHITECTURE.md`'s actual navigation tree (§2) has **no generic POI detail screen at all** — it jumps from list screens (`CollectionsScreen`, `FavoritesScreen`) directly to feature-specific screens (`HeritageNarrationScreen`), with nowhere for a non-heritage POI's rating, reviews, or favourite-toggle to live.
- **Source PRD section:** §25.1 (Key Screens).
- **Current implementation decision:** Implicitly assumed but never added to the navigation structure.
- **Why it is a problem:** Without this screen, Reviews (Must-adjacent, Should-priority, Phase 1) and general POI browsing beyond map pins have no defined mobile entry point.
- **Recommended resolution:** Add a `POIDetailScreen` to the `TripDetailStack` (and reachable from Collections/Favorites) hosting: POI info, favourite toggle, reviews (view + submit), and a link into `HeritageNarrationScreen` where applicable.

#### M11 — MEDIUM — Dynamic text translation has no endpoint

- **Problem:** FR-009's Phase 2 description reads: *"User can speak/type in their own language for live translation."* This describes two distinct capabilities — live **speech** translation and dynamic **text** translation of arbitrary (non-curated) input. `API_SPECIFICATION.md` §9 only defines `POST /translate/speech`; no text-translation endpoint exists anywhere.
- **Source PRD section:** FR-009 (§14), Module 8 (§12).
- **Current implementation decision:** Only the speech half of FR-009's Phase 2 scope was built out.
- **Why it is a problem:** This is one of the eight capabilities the audit explicitly asked to verify support for ("dynamic translation" as distinct from "live speech translation") — and as documented, arbitrary text translation genuinely has no implementation path, only the fixed/curated phrasebook (F10) and speech translation (F25).
- **Recommended resolution:** Add `POST /translate/text` alongside `/translate/speech` for Phase 2, or explicitly document that typed input is intentionally routed through the same speech-translation provider's text-translation capability (many providers support both) via the existing endpoint — either is fine, but it needs to be a stated decision.

---

### 2.8 Is the deployment architecture realistic for this project?

**Verdict: Directionally realistic (PaaS + managed Supabase is genuinely lean-team-appropriate), but three concrete gaps and one unacknowledged tension.**

#### H3 — HIGH — Redis/caching is silently absent despite being functionally required

- **Problem:** PRD §26.4's Recommended Technology Stack table has eight rows: Mobile/Frontend, Backend/API, AI Orchestration, Database, **Caching**, Object Storage, Notifications, Hosting. `IMPLEMENTATION_BLUEPRINT.md` §1.1 maps every row **except Caching** into the target architecture. Meanwhile, `API_SPECIFICATION.md` describes per-user rate-limit token buckets and 24h idempotency-key storage (M3), and `AI_ARCHITECTURE.md` §12 describes caching heritage-narration responses, weather, and Maps responses — all classic Redis use cases — with no concrete backing store named anywhere in `DEPLOYMENT_PLAN.md` or `DATABASE_SCHEMA.md`.
- **Source PRD section:** §26.4 (Recommended Technology Stack — Caching row: "Redis (session data, hot recommendation results)... Alternative: In-memory cache within the API layer for the earliest MVP").
- **Current implementation decision:** Not discussed anywhere. Unlike every other deviation from the PRD's stack table (Expo Push instead of raw FCM, PostGIS addition, FastAPI instead of Spring Boot), which were each explicitly justified in `IMPLEMENTATION_BLUEPRINT.md` §1, this one was never surfaced at all.
- **Why it is a problem:** This is the one place in the seven documents that matches the exact failure mode the task instructions warned against: *"Do not silently change the architecture."* Practically, it also has a real correctness consequence — rate limiting and idempotency-key deduplication implemented as in-process/local state will not work correctly the moment the FastAPI backend runs more than one instance (which `DEPLOYMENT_PLAN.md`'s own PaaS hosting model allows and expects at scale), silently breaking the exact NFR (§15, idempotent writes) these mechanisms exist to satisfy.
- **Recommended resolution:** Explicitly decide and document one of: (a) add Redis as a service in `DEPLOYMENT_PLAN.md` §2 (matching the PRD's Recommended row directly, most PaaS providers offer a managed Redis add-on cheaply), or (b) explicitly adopt the PRD's own named Alternative ("in-memory cache within the API layer for the earliest MVP") **with an explicit single-instance constraint stated in `DEPLOYMENT_PLAN.md`** until Redis is added. Either is PRD-compliant; leaving it undecided is not.

#### H4 — HIGH — No admin tool exists anywhere for the content pathway the MVP's core feature depends on

- **Problem:** `API_SPECIFICATION.md` §19 defines a full `/admin/*` surface (`POST /admin/pois`, `POST /admin/heritage-content`, `PATCH /admin/heritage-content/{id}/publish`, review moderation, KPI dashboard), and `AI_ARCHITECTURE.md` §5.1 depends on it for heritage-content ingestion. But `MOBILE_ARCHITECTURE.md` is entirely traveller-facing (React Native only) — **no document anywhere specifies what tool a content curator or admin actually uses** to call these endpoints: no admin web app, no CLI, no stated fallback (e.g. "use FastAPI's auto-generated `/docs` Swagger UI for MVP").
- **Source PRD section:** §41.1 (Internal Dependency: "Curated heritage content must be prepared and verified before the narration feature can ship for a given POI"), §22 (heritage narration is "the product's most distinctive capability").
- **Current implementation decision:** Full admin API designed; zero admin tooling/interface planned.
- **Why it is a problem:** This gates the single feature the PRD itself identifies as the product's core differentiator (§22, §43.1). Without *some* way to call these endpoints, the team cannot populate the 5–10 launch heritage POIs, and F8 cannot ship regardless of how well everything else is built.
- **Recommended resolution:** Make an explicit, cheap decision now rather than discovering this mid-sprint: for MVP, using FastAPI's built-in interactive `/docs` (Swagger UI) as the admin interface is a legitimate, zero-additional-build option, since it's already authenticated and functional — state this explicitly in `DEPLOYMENT_PLAN.md` or `IMPLEMENTATION_BLUEPRINT.md` as the deliberate Phase-1 choice, with a lightweight dedicated admin screen only if/when content-authoring volume justifies it.

#### M7 — MEDIUM — No separation of LLM cost/keys between staging and production

- **Problem:** `TESTING_PLAN.md` §2 and §4 run real LLM calls nightly against staging (golden-set regression + Maestro E2E), but `DEPLOYMENT_PLAN.md` §4 (Secrets Management) doesn't specify whether staging and production use separate LLM provider API keys or spend caps.
- **Source PRD section:** §38 (Risk: "LLM/API cost overrun at scale").
- **Current implementation decision:** Unaddressed.
- **Why it is a problem:** A runaway nightly test (e.g. a bug causing the golden-set suite to loop) could consume the same cost budget or hit the same rate limits as production traffic if they share credentials, with no isolation to contain the blast radius.
- **Recommended resolution:** Provision separate API keys (and, if the provider supports it, separate spend alerts/caps) for staging vs. production in `DEPLOYMENT_PLAN.md` §4.

#### M14 — MEDIUM — No scheduled heritage-content freshness review

- **Problem:** PRD §36 requires *"a defined cadence for reviewing heritage-content freshness and accuracy."* `DEPLOYMENT_PLAN.md` §5 (Scheduled Jobs) lists five automated jobs (expiry reminders, location-ping purge, personalization recompute, weather cache refresh, analytics rollup) — none of them is a content-review cadence, and none is proposed elsewhere either (content review is inherently a human/editorial process, not automatable, but the *cadence* itself — e.g. quarterly — was never stated).
- **Source PRD section:** §36.
- **Current implementation decision:** Omitted.
- **Why it is a problem:** Without a stated cadence, content review has no forcing function and will likely never happen until a factual error is reported.
- **Recommended resolution:** Add a documented (human-process, not necessarily automated) cadence — e.g. quarterly review of all published `heritage_content` — to `DEPLOYMENT_PLAN.md` §5 or a maintenance-process note.

#### M6 — MEDIUM — Full CI/testing rigor assumed affordable from day one

- **Problem:** `TESTING_PLAN.md` and `DEPLOYMENT_PLAN.md` together specify: lint+typecheck+unit+integration+contract+security-scan gates blocking every PR, a nightly full Maestro E2E suite, a nightly AI golden-set regression suite, weekly k6 performance runs, pre-release OWASP ZAP scans, and quarterly backup-restore drills — all starting from Phase 1.
- **Source PRD section:** §40 (Constraint: "small/student team assumed, which directly shaped the architecture recommendation"), §34 (Testing Strategy, which does ask for all these test *types* but does not specify cadence/rigor level for an MVP-stage team).
- **Current implementation decision:** Full rigor specified without an explicit "here's what's mandatory from commit one vs. what's added once the team has bandwidth" staging.
- **Why it is a problem:** Standing up and *maintaining* this full matrix (especially nightly E2E and pre-release ZAP scans) is real, ongoing DevOps/QA engineering investment. For a lean/student team racing to ship an MVP, this could meaningfully slow feature velocity if all of it is required simultaneously rather than phased in — a real tension between "production-quality" (explicitly requested) and "small team, fast MVP" (an explicit PRD constraint) that the current documents don't acknowledge or resolve.
- **Recommended resolution:** Explicitly stage the testing rigor: lint + unit + integration + contract tests blocking merge from day one (cheap, high-value); nightly E2E, ZAP, and k6 added once Phase-1 core features stabilize, rather than required from the first PR. State this staging explicitly rather than presenting the full matrix as uniformly immediate.

#### M5 — MEDIUM — Testcontainers needs a custom Postgres image (unaddressed)

- **Problem:** `TESTING_PLAN.md` §3.2 says integration tests spin up "a real Postgres container with `pgvector` + `postgis` extensions enabled" via Testcontainers — but the vanilla `postgres` Docker image doesn't include either extension. A custom/pre-built image (e.g. `supabase/postgres`, or a project-maintained Dockerfile layering both extensions) is required, and this detail is not mentioned anywhere.
- **Source PRD section:** N/A — CI/testing implementation detail.
- **Current implementation decision:** Assumed but not specified.
- **Why it is a problem:** A small team unfamiliar with this nuance could lose real setup time discovering it, or worse, ship integration tests that silently run against a Postgres without pgvector/PostGIS (extension-dependent tests would simply fail to even create the schema).
- **Recommended resolution:** Name the specific base image (`supabase/postgres` is the most direct choice, since it already matches the production extension set) in `TESTING_PLAN.md` §3.2.

---

### 2.9 Unnecessary complexity that could slow MVP completion

**Verdict: A handful of additions are individually reasonable but collectively worth a conscious trim/defer decision.**

#### M4 — MEDIUM — PostGIS adds real technology surface for a lean team

- **Problem:** `DATABASE_SCHEMA.md` §1 adds the PostGIS extension (`geography(Point,4326)`, GiST indexes, `ST_DWithin`) beyond the PRD's literal "PostgreSQL + pgvector." This was justified as "the standard, low-risk way" to do geofencing — but for an MVP with a curated catalog of dozens to low-hundreds of POIs (not millions of location points), a simpler `latitude double precision, longitude double precision` pair plus a bounding-box pre-filter and Haversine-formula distance check (computed in SQL or application code) would likely be adequate and removes an entire extension a small team needs to learn, enable, and keep working across local/CI/staging/production environments.
- **Source PRD section:** §26.4 (database row says "PostgreSQL + pgvector" only), §40 (lean-team constraint).
- **Current implementation decision:** PostGIS added as a default without presenting the simpler alternative as a real option.
- **Why it is a problem:** Not wrong, but a real complexity trade-off was made unilaterally rather than left as a conscious team choice — exactly the kind of decision this review's instructions asked to surface rather than resolve silently.
- **Recommended resolution:** Present both paths to the team explicitly: PostGIS (better long-term, more precise, one more extension to operate) vs. plain lat/lng + bounding-box math (zero extra dependency, sufficient at MVP scale, would need revisiting only if the POI catalog or location-ping volume grows by orders of magnitude). Let the team pick consciously rather than inheriting the choice made here.

#### L4 — LOW — Two LLM adapters implied for MVP; only one is needed

- **Problem:** `AI_ARCHITECTURE.md` §1 names `AnthropicAdapter` and `OpenAIAdapter` as concrete adapters to build, when MVP only needs one working provider at launch.
- **Source PRD section:** §26.4/§41.2 (provider deliberately unnamed).
- **Current implementation decision:** Both named as if both should be built.
- **Why it is a problem:** Building and testing a second, unused adapter is pure early effort with no MVP-stage payoff.
- **Recommended resolution:** Build the `LLMGateway` interface (cheap) and exactly one concrete adapter for MVP; add a second only when an actual provider-swap need arises.

#### L5 — LOW — Analytics rollup job may be premature

- **Problem:** `DEPLOYMENT_PLAN.md` §5 specifies a daily scheduled rollup job aggregating `analytics_events` into KPI views before any real usage data exists.
- **Source PRD section:** §37 (KPIs), Module 23 (Analytics, MVP-tagged).
- **Current implementation decision:** Pre-aggregation job specified from day one.
- **Why it is a problem:** At MVP scale, on-demand queries against the raw event table are almost certainly fast enough; the rollup job is optimization for a volume the product doesn't have yet.
- **Recommended resolution:** Defer the rollup job; query `analytics_events` directly for the admin KPI endpoint until volume actually requires pre-aggregation.

---

### 2.10 Anything missing from the PRD-to-implementation mapping

Beyond the specific endpoint/screen gaps already listed (H2, M9, M10, M11), two smaller mapping gaps:

#### L7 — LOW — Modules 11/12 (Attractions/POIs, Restaurants/Food) have no dedicated F-number

- **Problem:** Every other PRD Module (§12) got an explicit F-numbered entry in `IMPLEMENTATION_BLUEPRINT.md` — Modules 11 ("Attractions & Points of Interest") and 12 ("Restaurants / Food") did not. They are functionally covered (both are just `pois.category` values surfaced through F3's generation pipeline and F6's search endpoint), but this is never stated as an explicit traceability decision the way every other module was.
- **Source PRD section:** §12, Modules 11–12 (both MVP-tagged).
- **Current implementation decision:** Implicitly folded into shared POI infrastructure.
- **Why it is a problem:** Minor — a reader checking "is Module 12 covered?" against the Blueprint's feature list would not immediately find it.
- **Recommended resolution:** Add one sentence to `IMPLEMENTATION_BLUEPRINT.md` §2.2 confirming Modules 11 and 12 map onto F3/F6's shared POI mechanism rather than standalone features.

#### M13 — MEDIUM — "Data export" actions aren't wired to audit logging

- **Problem:** PRD §27 requires audit logging for three named action types: "data export, account deletion, admin content edits." `DEPLOYMENT_PLAN.md` §6 covers account deletion; `API_SPECIFICATION.md` §19's admin endpoints imply content-edit logging. But `GET /trips/{trip_id}/memory-items/export` (§10) — the concrete "data export" action — is never described as writing an `audit_logs` row anywhere.
- **Source PRD section:** §27.
- **Current implementation decision:** Two of three named audit categories are addressed; the third (export) is not.
- **Why it is a problem:** As documented, the memory-box export feature would ship without the audit logging §27 explicitly requires for it by name.
- **Recommended resolution:** Add an explicit note to `API_SPECIFICATION.md` §10 that the export endpoint writes an `audit_logs` row (`action = 'data_export'`).

---

### 2.11 Anything introduced that is NOT supported by the PRD

Two items beyond the already-covered PostGIS (M4) and Redis omission (H3):

#### M12 — MEDIUM — SMS/Email provider for SOS is a new, un-budgeted external dependency

- **Problem:** `IMPLEMENTATION_BLUEPRINT.md` F21 and `API_SPECIFICATION.md` §16 both introduce "SMS/email provider for trusted-contact notification if contact isn't an app user" for the Safety/SOS feature. The PRD's §24 (API & Third-Party Integrations) table lists exactly twelve integrations — Maps, OAuth, Weather, LLM, Translation (text), Translation (speech), Hotel link-out, Hotel/flight API, Places/POI, Push (FCM), Object storage, Payments — **none of which is an SMS or transactional-email service.** `DEPLOYMENT_PLAN.md` §4's secrets list also never includes an SMS/email provider key, so this dependency is both ungrounded in the PRD and internally inconsistent with my own deployment documentation.
- **Source PRD section:** §24 (no SMS/email row), FR-017 (§14): "trusted contact receives a link... is immediately notified" — mechanism unspecified.
- **Current implementation decision:** Added because a trusted contact is explicitly framed as not necessarily an app user, so *some* out-of-app channel is logically required for the feature to function at all — but this inference was never surfaced as a new cost/vendor decision.
- **Why it is a problem:** This is a real, necessary technical requirement (the feature cannot work without it) that was added silently rather than flagged as new scope requiring a business decision (a new vendor relationship, cost, and compliance surface — e.g. SMS delivery in India has regulatory/DLT-registration requirements worth knowing about ahead of time).
- **Recommended resolution:** Explicitly add "SMS/Email provider (e.g. Twilio, SendGrid, or an India-specific SMS gateway)" to the PRD-derived external dependencies list and to `DEPLOYMENT_PLAN.md` §4's secrets management, and flag it to the product owner as a new, PRD-unlisted cost line item requiring sign-off — it is very likely necessary (the feature doesn't work without it), but it should be a visible decision, not an inherited one.

#### L8 — LOW — Persona-level "accessibility-aware suggestions" never became a formal requirement or schema field

- **Problem:** The Family Traveller persona (§9) explicitly states a need for "accessibility-aware suggestions," but this was never promoted to a numbered FR/BR anywhere in the PRD, and correspondingly `pois` has no accessibility-related column (wheelchair access, elderly-friendly pacing flags, etc.) in `DATABASE_SCHEMA.md`.
- **Source PRD section:** §9 (persona needs), never elevated to §13/§14.
- **Current implementation decision:** Not addressed, consistent with the PRD itself never formalizing it.
- **Why it is a problem:** Not a defect in the seven documents (there's no FR to implement), but worth surfacing explicitly since the audit asked what's missing from the PRD-to-implementation mapping — this is a case where the gap originates in the PRD itself, not in translation.
- **Recommended resolution:** Flag to the product owner as a candidate for a future FR (e.g. Phase 2/3) rather than silently treating the persona need as satisfied.

---

### 2.12 Assumption Log — every place the PRD was ambiguous

| # | Assumption made | Why the PRD was ambiguous | Risk if wrong | Related finding |
|---|---|---|---|---|
| A1 | Visual Q&A (FR-008) placed in Phase 1, sequenced after Must-haves | Module table (§12) tags it MVP; FR-level priority (§14) is "Should"; §29.1's MVP bullet list omits it entirely | Low — worst case, over-built relative to stakeholder expectation of a leaner Phase 1 | `IMPLEMENTATION_BLUEPRINT.md` §2.1 Note 1 |
| A2 | Post-Trip Feedback Capture (FR-018) placed in Phase 1 | Not bucketed in §29.1/29.2/29.3 at all; priority "Should" | Low — cheap feature, high signal value even if descoped | §2.1 Note 2 |
| A3 | Analytics treated as cross-cutting instrumentation, not a screen | Module 23 tagged MVP with no described UI | Low — reasonable reading, no PRD screen exists to contradict it | §2.1 Note 3 |
| A4 | §31's 4-phase split (not §29.3's coarser 3-phase lump) used as authoritative for Phase 3 vs. 4 boundary | §29.3 and §31 genuinely disagree on granularity | Low — §31 is strictly more specific, doesn't contradict §29.3 | §2.1 Note 4 |
| A5 | "Edit rights" concept for group-trip itinerary editing | PRD never defines role-based permissions beyond organiser/member | **Medium** — currently unresolved and inconsistent with the DB (see H5) | H5 |
| A6 | Group-trip memory box / expenses / raw notes treated as fully shared (any member can edit/delete any other member's rows) | PRD's memory-box language predates group-trip consideration; never states per-member privacy within a shared trip | **High** — a co-traveller can delete another's content (see H6) | H6 |
| A7 | SMS/Email provider assumed necessary for SOS trusted-contact notification | PRD states a trusted contact may not be an app user but never names a notification mechanism | Medium — almost certainly correct that *something* like this is needed, but was never surfaced as a new cost decision | M12 |
| A8 | Embedding model defaulted to an unnamed 1536-dimension model | PRD never names an embedding model/provider | Low — explicitly flagged as configurable in `AI_ARCHITECTURE.md` §1, re-embedding cost on change already documented | — |
| A9 | Memory-box behavior *after* the 12-month expiry reminder if the user takes no action | PRD (§43.3) explicitly flags this as an open question ("what actually happens at the 12-month mark") without resolving it | Low — correctly left as an explicit open decision requiring legal/policy sign-off, not silently assumed | `DATABASE_SCHEMA.md` §6 |
| A10 | RPO/RTO, concurrent-user targets, onboarding numeric pass bar, AI-accuracy pass bar all left as Proposed/TBC | PRD itself marks these TBC (§15, §39) | Low — consistent with PRD's own posture, correctly not invented | Multiple docs |
| A11 | Data-deletion SLA proposed at "within 30 days" | PRD doesn't state one; analogous fields elsewhere marked "TBC pending legal/financial input" | Low — explicitly marked Proposed/TBC, not asserted as final | `DEPLOYMENT_PLAN.md` §6 |
| A12 | Phase 3/4 stub tables (`bookings`, `trip_recaps`) created in the same migration set as Phase 1 tables rather than deferred | PRD (BR-013) asks for "design-for-future" without specifying *when* the physical schema should exist | Low — harmless (empty tables), but should be a conscious choice, not an implicit one | §2.14 (below) |
| A13 | Redis/caching silently dropped from the target stack rather than explicitly adapted like every other stack deviation | N/A — this is not a PRD ambiguity, it is an internal omission (the PRD is clear that caching belongs in the stack) | **High** | H3 |

**Note on A13:** every other place this project's architecture deviates from the PRD's stack table (Expo Push vs. raw FCM, FastAPI vs. Spring Boot, PostGIS addition) was explicitly named and justified in `IMPLEMENTATION_BLUEPRINT.md` §1. The Caching row was not — it wasn't resolved ambiguously, it was simply never addressed. This is called out here plainly rather than folded quietly into the "ambiguity" framing, because it isn't one.

---

### 2.13 Capability verification

| Capability | Supported? | Notes |
|---|---|---|
| Dynamic (text) translation | **Partial — gap found** | Curated phrasebook (F10) and speech translation (F25) are both implemented; arbitrary typed-text translation described in FR-009's Phase 2 flow has no endpoint. See M11. |
| Live speech translation | Yes | F25, `POST /translate/speech`, correctly scoped to Phase 2/3 per §43.4, with a documented fallback to the static phrasebook. |
| Visual Q&A | Yes | F9, full pipeline in `AI_ARCHITECTURE.md` §6, correctly scoped to heritage-POI context matching FR-008's own preconditions. Logging gap noted at M8. |
| Heritage RAG | Yes | F8, the most thoroughly specified pipeline in the entire document set (`AI_ARCHITECTURE.md` §5) — ingestion, chunking, retrieval, grounding contract, confidence flagging, golden-set evaluation all present and mutually consistent. |
| Location-aware companion | Yes, with caveats | F7 core arrival-detection is solid. The Dynamic Re-Adaptation extension (F20, Phase 2) has the endpoint contradiction at H2. The PostGIS dependency (M4) is a complexity trade-off, not a functional gap. |
| Memory Box | Yes, with a defect | F11 is architecturally complete (upload, retention, reminder, export) but has the RLS over-permissiveness defect at H6. |
| Hotel/flight integration | **Correctly stubbed, not functional** | F27/`bookings` table/`/bookings` endpoint (501) exist exactly as BR-013 asks — "design-for-future," not real integration pre-MVP. This is intentional and matches §43.7 precisely, not a gap. |
| AI itinerary modification | Yes | F5, `AI_ARCHITECTURE.md` §4 — scoped-diff mechanism directly satisfies FR-004's "only the relevant segment changes" acceptance criterion. |

---

### 2.14 Do future features accidentally become mandatory MVP dependencies?

**Verdict: Mostly no, with one structural coupling worth naming explicitly.**

The RLS policy protecting the core `trips` table (used by every Phase-1 solo trip) references `trip_members` — a table whose only *feature* owner is F19 (Group Planning, Phase 2):

```sql
create policy "trips_select_member" on public.trips
  for select using (
    auth.uid() = owner_id
    or exists (select 1 from public.trip_members m where m.trip_id = trips.id and m.user_id = auth.uid())
  );
```

This means `trip_members` (and the `is_trip_member()` helper function built on it) must physically exist from the very first Phase-1 migration, purely so the RLS policy on `trips` can be defined at all — even though no Phase-1 feature ever writes to it. This is not harmful (creating an empty table costs nothing operationally) and does not pull any Phase-2 *application code* into Phase 1 — but it is a real, silent schema-level coupling that should be named explicitly rather than left implicit, exactly as the audit's item 14 asks. Similarly, `budget_expenses.split_with` (Phase-2 group-splitting field) is present on the same table/endpoint documented for Phase-1 individual tracking (F15) without a clear visual boundary in `API_SPECIFICATION.md` §14 marking which fields are Phase-2-only — a minor risk that a Phase-1 implementer builds group-splitting logic prematurely, or a Phase-1 API consumer sends a field the backend isn't yet meant to honor.

- **Recommended resolution:** No architectural change needed. Add a one-line note to `DATABASE_SCHEMA.md` §4 (`trip_members`) and §8 (`budget_expenses`) stating explicitly: "table/field exists from the Phase-1 migration for schema stability, but is not written to by any Phase-1 feature" — so this is a documented decision, not a discovered surprise.

---

### 2.15 Can a small development team build this within the current timeline?

**Verdict: Cannot be fully verified — and that itself is worth stating plainly rather than glossing over.** The PRD explicitly leaves "Team size" and "Time" as TBC constraints (§40): *"Budget: limited/self-funded or hackathon-scale... Team size: small/student team assumed... Time: hackathon/academic timeline assumed — exact duration TBC."* Without a real team-size and calendar-time figure, no document — including this one — can responsibly assert "yes, this fits."

What can be said concretely:

- **M15 — MEDIUM — No effort/timeline estimate exists to sanity-check feasibility.** Even correctly scoped to Phase 1 only, the MVP surface is substantial: 18 features (F1–F18), roughly two dozen actively-used database tables, ~19 API endpoint groups, and a non-trivial RAG content pipeline that requires real editorial/content work (curating and verifying 5–10 flagship heritage POIs) in parallel with engineering — not just code. None of the seven planning documents attempts a story-point or week-level effort estimate against this scope. **Recommended resolution:** before implementation begins, run a lightweight estimation pass (even a rough T-shirt-sizing exercise) against the F1–F18 list in `IMPLEMENTATION_BLUEPRINT.md` §3, using the actual team's size and available calendar time, and use `IMPLEMENTATION_BLUEPRINT.md` §8's build-sequencing order to identify where the plan would need to cut scope if the estimate doesn't fit.
- The specific complexity items already flagged in §2.9 (PostGIS, full CI/test rigor from day one, dual-layer RLS+backend authorization) are the most likely places where trimming would recover real time if the estimation pass in M15 shows the team is over capacity — each has an explicit lighter-weight alternative named in this review.
- The content-pipeline dependency (§41.1, tied to H4's admin-tooling gap) is the least "engineering-shaped" risk to team velocity: heritage content curation is editorial work that doesn't parallelize the same way engineering tasks do, and no document currently accounts for who does this work or how long it takes.

---

## 3. Recommended Remediation Order

Before implementation begins, in priority order:

1. **Fix C1 and C2** (add `pace` column; fix `audit_logs.actor_user_id` FK) — trivial schema edits, both silently break Must-priority requirements if shipped as-is.
2. **Resolve H1** (auth/profile-provisioning mechanism — pick trigger *or* endpoint, not an unreconciled mix of both across three documents) since it's the very first thing built.
3. **Decide H3** (Redis vs. explicitly-documented single-instance constraint) before any endpoint that depends on rate limiting or idempotency keys is implemented.
4. **Decide H4** (admin tooling — even "use `/docs` for now" is a valid, fast decision) before heritage-content curation work needs to start, since it's a day-1-of-Phase-1 dependency.
5. **Fix H6** (tighten memory-box/expense/notes RLS) before Phase 2 group trips ship — cheap now, a real user-trust incident later if missed.
6. **Add H7's missing weather validation step** before F3 (Itinerary Generation) is implemented, since it's Phase-1, Must-priority, and cheap to add now vs. retrofit later.
7. **Reconcile H2 and H5** before Phase 2 (Dynamic Re-Adaptation, Group Planning) implementation begins — not MVP-blocking, but should not carry an unresolved contradiction into that work.
8. Address the MEDIUM items opportunistically as their owning feature is implemented (each is scoped to a single document/table and independently fixable).
9. Run the M15 effort-estimation pass in parallel with the above — it doesn't block starting Phase-1 engineering work, but should inform scope decisions before the team commits to a launch date.

No finding in this review requires re-architecting the system described in the seven planning documents.
