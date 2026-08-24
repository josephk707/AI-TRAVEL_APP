# Implementation Blueprint
## AI-Powered Personalized Tourist Guide & Travel Companion (TC-SO1)

| | |
|---|---|
| Source of truth | `docs/AI_Tourist_Guide_Master_PRD_SDLC.pdf` (Master PRD & SDLC, v1.0, 21-Aug-2026) |
| Companion documents | `DATABASE_SCHEMA.md` · `API_SPECIFICATION.md` · `AI_ARCHITECTURE.md` · `MOBILE_ARCHITECTURE.md` · `DEPLOYMENT_PLAN.md` · `TESTING_PLAN.md` |
| Status | Planning — no application code written yet |
| Prepared by | Engineering (acting as CTO / Architect / PM / Full-Stack / AI / DB / Mobile / QA / DevOps) |

This document is the master implementation reference. It fixes the target architecture, resolves the few places the PRD leaves open (marked `TBC`/`Proposed Target`), and — for every feature in the PRD — specifies the ten dimensions requested: frontend component, backend API, database tables, external API, AI component, auth/authz requirement, error handling, testing requirement, dependencies, and implementation priority/phase.

No feature below was invented outside the PRD. Where the PRD itself is ambiguous (a module tagged one phase in one section and a different phase in another), the resolution is stated explicitly and traced back to the source section, never silently decided.

---

## 1. Target Architecture (fixed)

```
React Native + Expo (mobile client, iOS + Android)
        ↓  HTTPS / REST + JSON, Supabase JS client for auth token refresh
FastAPI (Python) — API / Backend layer
        ↓
Business Logic Layer (Python services/domain modules inside the FastAPI app)
        ↓
AI / RAG Services (LLM orchestration, RAG, recommendation engine — Python services, same backend process/pool)
        ↓
External APIs (Google Maps Platform, Google OAuth, Weather, Translation, Places, FCM via Expo Push, hosted LLM + embedding provider)
        ↓
Supabase (PostgreSQL 15 + pgvector extension, Row Level Security, Object Storage, Auth)
```

### 1.1 Why this satisfies the PRD (traceability)

The PRD's Section 26.4 "Recommended Technology Stack" names Java + Spring Boot as its **primary recommendation** but explicitly lists **Python + FastAPI** as the **Alternative** for the API/Backend layer, **PostgreSQL + pgvector** as the **Recommended** database (this document's choice, unchanged), and a **PaaS "to minimise DevOps overhead"** as the Alternative hosting model. Supabase is a managed Postgres + pgvector + Storage + Auth PaaS, which is a direct, PRD-sanctioned instantiation of that alternative — it is not a deviation from the PRD, it is the explicitly-permitted lean-team path referenced in Section 40 (Constraints: "small/student team assumed... shaped the architecture recommendation") and Section 26.4's own framing ("what is realistic for a lean team to build and actually ship").

React Native is the PRD's **primary recommendation** for the mobile layer (Section 26.4); Expo is the standard managed tooling on top of React Native and is adopted here to minimize native build/DevOps overhead, consistent with the same lean-team framing.

| PRD stack row (Section 26.4) | PRD Recommended | PRD Alternative | This project uses | Fit |
|---|---|---|---|---|
| Mobile/Frontend | React Native | Flutter / React web | **React Native + Expo** | PRD-recommended, + managed tooling |
| Backend/API | Java + Spring Boot | **Node.js/Express or Python+FastAPI** | **Python + FastAPI** | PRD-listed alternative |
| AI Orchestration | Backend service calling hosted LLM API | Dedicated Python microservice | **FastAPI service module calling hosted LLM API** | Matches Recommended row directly |
| Database | **PostgreSQL + pgvector** | Managed vector DB (Pinecone) at scale | **PostgreSQL + pgvector (via Supabase)** | Exact match |
| Object Storage | S3-compatible | Firebase Storage/Cloudinary | **Supabase Storage (S3-compatible)** | PRD-recommended row |
| Notifications | Firebase Cloud Messaging | OneSignal | **Expo Push Notifications (built on FCM/APNs)** | Delivers FCM under the hood; see §1.2 |
| Hosting | Managed cloud (containerised) | **PaaS to minimise DevOps overhead** | **Containerised FastAPI on a PaaS (Render/Railway/Fly.io) + Supabase managed DB** | PRD-listed alternative |
| Auth | Google OAuth2 only, no first-party passwords | — | **Google OAuth2 via Supabase Auth** | Section 26.2 requirement met; Supabase is the OAuth2 broker + session/token issuer |

### 1.2 One deliberate adaptation, stated explicitly

The PRD recommends Firebase Cloud Messaging (FCM) directly for push notifications (Section 24, Section 26.4). Because the client is Expo-managed React Native, this project uses **Expo's Push Notification service**, which is Expo's standard abstraction over FCM (Android) and APNs (iOS) — it is the same delivery mechanism the PRD asks for, reached through the tool the mobile framework itself provides, and avoids hand-rolling native FCM SDK integration inside an Expo-managed app. No PRD requirement changes as a result (Module 20, FR-006 arrival notifications, FR-014 disruption notices, FR-010 memory-box expiry reminders, FR-017 SOS alerts all still function identically from the user's perspective).

### 1.3 Authentication & Authorization (Section 26.2, BR-002, FR-002)

- **Identity provider:** Google OAuth2 only, brokered through **Supabase Auth**. No first-party password storage anywhere in the system — matches Section 27 exactly.
- **Session handling:** Supabase issues short-lived JWT access tokens + refresh tokens; the Expo client uses `@supabase/supabase-js` (React Native storage adapter) to persist and silently refresh sessions (satisfies FR-002's "returning user... signed in silently").
- **API authorization:** every FastAPI endpoint validates the Supabase-issued JWT (via Supabase's JWKS) on each request; a `get_current_user` dependency injects the authenticated user/role into every route handler.
- **Authorization model:** role-based — `traveller` (default) and `admin` (internal content/moderation tooling), per Section 26.2. Row Level Security (RLS) policies in Postgres are a second, defense-in-depth layer directly on the tables (a compromised API token still cannot read another user's rows) — see `DATABASE_SCHEMA.md` §RLS.
- **No partial accounts:** if OAuth consent is denied or the callback fails, no `profiles` row is created (FR-002 exception flow) — enforced by only provisioning the profile row after a verified Supabase session exists (via a Supabase Auth `on_auth_user_created` trigger, not a client-trusted call).

### 1.4 AI Provider Strategy

The PRD deliberately avoids naming a specific LLM vendor ("hosted LLM API", Section 26.4; "no self-hosted models") and lists LLM/AI provider selection as an external dependency (Section 41.2). This project therefore implements an **LLM Gateway abstraction** inside the AI/RAG service layer (interface + adapter pattern) so the concrete provider (e.g. a Claude or GPT-class model for generation, a text-embedding model for RAG) is a configuration choice, not an architectural one — full detail in `AI_ARCHITECTURE.md`. This also directly serves Section 24's fallback requirement ("Fallback to curated templates/cached answers" if the LLM is unavailable) and Section 38's cost-overrun risk mitigation (provider/model can be swapped without a rewrite).

---

## 2. Phase Roadmap (authoritative mapping)

The PRD's Section 31 (Product Roadmap) gives the most granular 4-phase breakdown and is treated as authoritative here. Section 29 (MVP Definition) and Section 30 (MoSCoW) are coarser restatements of the same scope and are reconciled into this table; every reconciliation is noted in the "Resolution note" column so no scope is silently added or dropped.

| Phase | PRD name (§31) | Scope |
|---|---|---|
| **Phase 1 — MVP** | Core Personalised Travel Planning | §29.1 bullet list, below |
| **Phase 2** | Intelligent Travel Companion | §29.2 bullet list, below |
| **Phase 3** | Travel Ecosystem | Booking + payments, partner network, offline mode |
| **Phase 4** | Advanced AI Companion | Predictive/proactive AI, trip recap, "what if?" simulation, expanded heritage pipeline |

### 2.1 Resolution notes (ambiguities in the source PRD, resolved)

1. **Visual Q&A (FR-008 / Module 7):** Module table (§12) tags it **MVP**; FR-level priority (§14) is **Should**; the §29.1 MVP bullet list omits it. **Resolution:** included in Phase 1, sequenced after the Must-have items, consistent with §12's phase tag — the §14 "Should" priority governs build order within the phase, not which phase it belongs to.
2. **Post-Trip Feedback Capture (FR-018):** not explicitly bucketed in §29.1/29.2/29.3, priority **Should** (§14), directly feeds the Personalisation Engine which is core MVP thesis (§20). **Resolution:** included in Phase 1 — it is the lowest-cost, highest-signal-value item in the entire PRD (§37 KPI table calls it out) and the "After the Trip" user journey (§10.3) is part of the MVP-scoped core loop.
3. **Analytics (Module 23):** tagged MVP (§12), no dedicated screen. **Resolution:** implemented as cross-cutting instrumentation from Phase 1 day one (event logging + KPI funnel per §37), not a standalone user-facing feature.
4. **§29.3 "Phase 3/Advanced"** lumps booking, offline mode, AI recap, predictive recs, and group-reconciliation together. §31 splits these into Phase 3 (Travel Ecosystem: booking, payments, partner network, offline mode) vs. Phase 4 (Advanced AI Companion: recap, predictive, what-if, heritage-pipeline scale-up). **Resolution:** §31's split is used as authoritative below since it is strictly more specific and does not contradict §29.3, only refines it.

### 2.2 Phase 1 — MVP feature list

Auth · Onboarding · AI Conversational Planner & Itinerary Generation · Conversational Modification · User-Provided Trip Ideas · Maps & Navigation · Real-Time Location Companion & Arrival Notifications · Heritage Narration (5–10 flagship POIs) · Visual Q&A · Basic Text Phrasebook · Trip Memory Box · Trips List / Trip Management · Collections & Favourites · Basic Reviews · Budget Estimate (planning-time only) · Notifications · Post-Trip Feedback Capture · Analytics (internal instrumentation).

### 2.3 Phase 2 — Intelligent Travel Companion

Group/Collaborative Trip Planning · Dynamic Itinerary Re-Adaptation · Safety/SOS Trusted-Contact Sharing · Weekend/Local Outing Quick Plan · Budget Tracking with group expense splitting · Expanded heritage POI catalog · Live Speech Translation (via licensed API) · Offline Heritage Access (Recommended Enhancement).

### 2.4 Phase 3 — Travel Ecosystem

Automated hotel/flight booking via partner APIs · Payments · Partner network expansion · Offline mode for maps.

### 2.5 Phase 4 — Advanced AI Companion

AI-generated trip recap/shareable memory summaries · Predictive/proactive recommendations · "What if?" trip simulation · Richer model-assisted group preference reconciliation · Heritage catalog scaled via repeatable content pipeline.

---

## 3. Feature Blueprint — Phase 1 (MVP)

Each entry below maps 1:1 to a PRD Business Requirement (BR) and Functional Requirement (FR). Table/endpoint/pipeline/screen **names** are fixed here for consistency across all companion documents; full column/schema/payload detail lives in the referenced document.

### F1 — Google OAuth Sign-In
*BR-002, FR-002*

| Dimension | Detail |
|---|---|
| Frontend component | `AuthStack` → `SignInScreen` (Expo `AuthSession` + `supabase-js` Google provider) — see `MOBILE_ARCHITECTURE.md` §Navigation |
| Backend API | `POST /v1/auth/session/bootstrap` (idempotent profile provisioning after first Supabase login), `POST /v1/auth/logout` — see `API_SPECIFICATION.md` §Auth |
| Database tables | `profiles` (provisioned via Supabase Auth trigger, not client-writable) |
| External API | Google OAuth2 (brokered by Supabase Auth) |
| AI component | None |
| Auth/authz | This *is* the auth primitive; all other endpoints depend on it |
| Error handling | Consent denied/OAuth failure → no row created, sign-in screen re-shown with retry (FR-002 exception flow); network failure → retry affordance, no silent partial state |
| Testing requirement | OAuth redirect + token exchange integration test (mocked Google IdP in staging); "denied consent creates no account" regression test; session-refresh unit test |
| Dependencies | Supabase project + Google Cloud OAuth client configured before any other feature can be tested end-to-end |
| Priority / Phase | **Must — Phase 1**, first item built |

### F2 — Onboarding Interest & Traveller-Type Capture
*BR-019, FR-003*

| Dimension | Detail |
|---|---|
| Frontend component | `OnboardingStack` (≤6 screens per NFR Usability target, §15): pace, budget bracket, interest themes — single/multi-select |
| Backend API | `POST /v1/onboarding/responses`, `GET /v1/onboarding/status` |
| Database tables | `profiles`, `interests`, `profile_interests` |
| External API | None |
| AI component | None (raw signal capture only — consumed later by Personalization Engine, `AI_ARCHITECTURE.md` §Personalization) |
| Auth/authz | Authenticated traveller only |
| Error handling | Save failure does not block progression to home; defaults used, retry happens silently in background (FR-003 exception flow) |
| Testing requirement | Skip-path test (defaults applied without error); "first itinerary reflects ≥1 selected interest" regression test (ties to US-004) |
| Dependencies | F1 (Auth) |
| Priority / Phase | **Must — Phase 1** |

### F3 — AI Conversational Planner & Personalised Itinerary Generation
*BR-001, FR-001*

| Dimension | Detail |
|---|---|
| Frontend component | `ChatScreen` (companion chat, primary interaction surface per §25) + `ItineraryViewScreen` (map + timeline hybrid) |
| Backend API | `POST /v1/trips`, `POST /v1/trips/{trip_id}/itinerary/generate` — see `API_SPECIFICATION.md` §Trips & Itinerary |
| Database tables | `trips`, `itinerary_days`, `itinerary_items`, `pois` |
| External API | Google Places/Maps (POI candidates, geocoding), Weather API (outdoor-activity flagging), hosted LLM provider |
| AI component | **Itinerary Generation Pipeline** (LLM + hybrid recommendation engine + business-rule validator) — `AI_ARCHITECTURE.md` §Itinerary Generation |
| Auth/authz | Authenticated traveller; trip rows scoped to owner via RLS |
| Error handling | Missing inputs → ≤2–3 targeted clarifying questions, not a hard failure (FR-001 alt. flow); AI layer timeout/failure → curated fallback itinerary template + flagged "live generation failed" (FR-001 exception flow) |
| Testing requirement | Golden-set itinerary tests (budget/time/interest fit), budget-tolerance business-rule test (>10% over → flagged, §16), latency test against NFR target (8–12s, §15) |
| Dependencies | F1, F2, Places/Maps API key, LLM Gateway, business-rule validator |
| Priority / Phase | **Must — Phase 1**, core value proposition |

### F4 — Incorporate User-Provided Trip Ideas
*BR-012, FR-005*

| Dimension | Detail |
|---|---|
| Frontend component | Free-text "My own ideas" input inside `TripCreationScreen`, part of `ChatScreen` composer |
| Backend API | `POST /v1/trips/{trip_id}/notes` |
| Database tables | `trip_raw_notes` |
| External API | Hosted LLM provider (structured-element extraction) |
| AI component | **Idea Extraction** step, pre-processing stage of the Itinerary Generation Pipeline — `AI_ARCHITECTURE.md` §Idea Extraction |
| Auth/authz | Authenticated traveller, trip owner only |
| Error handling | Nothing extractable → raw notes still passed to planner as context, never discarded (FR-005 alt. flow); conflicting/unrealistic combinations (e.g. two distant cities same day) → flagged, not silently resolved (FR-005 exception flow) |
| Testing requirement | "Named places in pasted notes appear in generated plan" regression test (ties to US-002, BR-012 traceability row) |
| Dependencies | F3 |
| Priority / Phase | **Must — Phase 1** |

### F5 — Conversational Itinerary Modification
*FR-004*

| Dimension | Detail |
|---|---|
| Frontend component | `ChatScreen` inline diff/preview of proposed itinerary segment change |
| Backend API | `POST /v1/trips/{trip_id}/itinerary/modify` |
| Database tables | `itinerary_items`, `ai_conversations`, `ai_messages` |
| External API | Hosted LLM provider |
| AI component | **Conversational Modification Pipeline** — interprets request against current itinerary + profile, proposes a scoped diff |
| Auth/authz | Trip owner or trip member with edit rights (group trips, Phase 2) |
| Error handling | Ambiguous request → single clarifying question, not a guess (FR-004 alt. flow); request violates a hard business rule (opening hours, etc.) → explain conflict + propose closest valid alternative (FR-004 exception flow) |
| Testing requirement | "Only the relevant segment changes, rest of plan preserved" regression test; invalid-change explanation test |
| Dependencies | F3 |
| Priority / Phase | **Must — Phase 1** |

### F6 — Maps & Navigation
*Module 9*

| Dimension | Detail |
|---|---|
| Frontend component | `react-native-maps` (Google provider) embedded in `ItineraryViewScreen` and `OnTripCompanionScreen` |
| Backend API | `GET /v1/pois/{id}`, `GET /v1/pois/search` (thin proxy/cache in front of Places API, never exposes raw Maps key to client) |
| Database tables | `pois` |
| External API | Google Maps Platform (Maps SDK, Places, Directions, Geocoding) |
| AI component | None |
| Auth/authz | Authenticated traveller |
| Error handling | Map tiles fail to load → degrade to list view (§24 fallback) |
| Testing requirement | POI search/geocode contract test; map-tile-failure fallback UI test |
| Dependencies | Google Maps Platform API key/billing account |
| Priority / Phase | **Must — Phase 1** |

### F7 — Real-Time Location Companion & Arrival Notifications
*BR-003, FR-006*

| Dimension | Detail |
|---|---|
| Frontend component | `OnTripCompanionScreen` (glanceable, on-trip UX mode per §25.2), background location task (`expo-location` + `expo-task-manager`) |
| Backend API | `POST /v1/trips/{trip_id}/location/ping`, `GET /v1/trips/{trip_id}/nearby` |
| Database tables | `location_pings` (ephemeral, active-trip only, see retention rule §DATABASE_SCHEMA.md), `itinerary_items` |
| External API | Google Maps Platform (geofencing/distance calc) |
| AI component | Nearby-recommendation ranking uses the Personalization/Recommendation Engine (hybrid rules + embeddings) |
| Auth/authz | Authenticated traveller, active-trip scoped, **explicit per-trip opt-in consent required before any location write** (BR-014) |
| Error handling | Permission denied/unavailable → location-dependent features disabled gracefully, manual "I'm at ___" fallback, rest of app unaffected (FR-006 exception flow) |
| Testing requirement | Geofence-entry → notification-within-target-latency test; permission-denied fallback test; consent-gate security/privacy test |
| Dependencies | F3 (active itinerary must exist), Expo Push setup, Maps API |
| Priority / Phase | **Must — Phase 1** |

### F8 — On-Site Heritage & Cultural Narration
*BR-004, FR-007*

| Dimension | Detail |
|---|---|
| Frontend component | `HeritageNarrationScreen` — layered content (overview → deep detail), sub-section navigation as user physically moves (§22) |
| Backend API | `GET /v1/heritage/{poi_id}/narration` |
| Database tables | `pois`, `heritage_content`, `heritage_content_embeddings` |
| External API | None at request time (curated content, pre-ingested) |
| AI component | **Heritage Narration RAG Pipeline** (pgvector retrieval → grounded LLM composition → confidence flag) — `AI_ARCHITECTURE.md` §RAG Pipeline. Covers a curated shortlist of **5–10 flagship POIs** at launch (§29.1, §43.1) |
| Auth/authz | Authenticated traveller |
| Error handling | Unsupported POI → states so plainly, logs as a coverage request, never fabricates (FR-007 exception flow); partial content → shows verified portion, marks rest unavailable (FR-007 alt. flow) |
| Testing requirement | **Golden-set regression suite** — versioned known-correct facts per launch POI, re-run on every prompt/retrieval change (§34); load-time NFR test |
| Dependencies | Curated + verified heritage content ingested and embedded *before* a POI can ship (§41.1 Internal Dependency) |
| Priority / Phase | **Must — Phase 1 (curated set)** — product's most distinctive capability (§22) |

### F9 — Photo-Based Landmark Q&A (Visual Q&A)
*BR-005, FR-008*

| Dimension | Detail |
|---|---|
| Frontend component | `PhotoQAScreen` — camera/upload + question composer, reachable from `HeritageNarrationScreen` |
| Backend API | `POST /v1/heritage/{poi_id}/photo-qa` |
| Database tables | `heritage_content`, `heritage_content_embeddings`, `ai_messages` (answer logged for audit/eval) |
| External API | None beyond LLM provider |
| AI component | **Visual Q&A Pipeline** — multimodal LLM call grounded against the same POI RAG content; low-confidence answers explicitly flagged (§19, FR-008 business rule) |
| Auth/authz | Authenticated traveller |
| Error handling | Image analysis failure (poor quality/unsupported format) → asks for retake, never guesses from an unusable image (FR-008 exception flow); no confident POI match → answers as generally as confidently possible + invites rephrase (FR-008 alt. flow) |
| Testing requirement | Grounded-answer relevance test against a golden photo set; low-confidence visible-flag test |
| Dependencies | F8 (heritage content must exist for the POI) |
| Priority / Phase | **Should → built in Phase 1** (§12 module phase tag; see Resolution Note 1, §2.1) |

### F10 — Local Phrase Assistant (Text Phrasebook)
*BR-006, FR-009*

| Dimension | Detail |
|---|---|
| Frontend component | `PhrasebookScreen` — category browse/search, local script + phonetic transliteration; downloadable per-trip for offline use |
| Backend API | `GET /v1/phrasebook/{region}`, `POST /v1/trips/{trip_id}/phrasebook/download` |
| Database tables | `phrasebook_entries` |
| External API | None for MVP (curated content); Translation API reserved for Phase 2 live translation |
| AI component | None (static curated content) |
| Auth/authz | Authenticated traveller |
| Error handling | No content yet for a region → states this clearly, no broken/empty screen (FR-009 exception flow); offline after pre-download → phrases still load from local cache (business rule, §14) |
| Testing requirement | Offline-availability test (airplane-mode); multi-language-region selection test |
| Dependencies | Curated phrasebook content authored per target region before regional launch |
| Priority / Phase | **Should → built in Phase 1** |

### F11 — Trip Memory Box (Upload, View, Download)
*BR-007, FR-010*

| Dimension | Detail |
|---|---|
| Frontend component | `MemoryBoxScreen` (per-trip gallery), upload flow from `OnTripCompanionScreen` and post-trip |
| Backend API | `POST /v1/trips/{trip_id}/memory-items`, `GET /v1/trips/{trip_id}/memory-items`, `GET /v1/trips/{trip_id}/memory-items/export` |
| Database tables | `memory_items` |
| External API | Supabase Storage (S3-compatible object storage) |
| AI component | None in Phase 1 (Phase 4 adds AI trip-recap generation over this data) |
| Auth/authz | Trip owner/member only; encrypted at rest (§27) |
| Error handling | Upload fails (network/size) → retry or clearly reported failure, never silently dropped (FR-010 exception flow); approaching 12-month retention → reminder + one-tap download/extend, **never silent deletion** (§43.3, business rule) |
| Testing requirement | Upload/download/retention-reminder test; expiry-job dry-run test verifying no silent deletion occurs |
| Dependencies | F1, Supabase Storage bucket + signed-URL policy |
| Priority / Phase | **Must — Phase 1** |

### F12 — Trip Management (Trips List)
*Module 15*

| Dimension | Detail |
|---|---|
| Frontend component | `TripsListScreen` — grouped by upcoming/active/completed (US-020) |
| Backend API | `GET /v1/trips`, `PATCH /v1/trips/{trip_id}` (status transitions), `DELETE /v1/trips/{trip_id}` (soft-delete) |
| Database tables | `trips` |
| External API | None |
| AI component | None |
| Auth/authz | Authenticated traveller, owner/member scoped |
| Error handling | Cancel → soft-delete/archive, memory-box items already added are unaffected (§28 edge case) |
| Testing requirement | Status-grouping test; soft-delete-preserves-memories regression test |
| Dependencies | F3 |
| Priority / Phase | **Must — Phase 1** |

### F13 — Collections & Favourites
*BR-008, FR-011*

| Dimension | Detail |
|---|---|
| Frontend component | `CollectionsScreen`, favourite toggle on any POI card |
| Backend API | `POST /v1/favorites`, `POST /v1/collections`, `POST /v1/collections/{id}/items` |
| Database tables | `favorites`, `collections`, `collection_items` |
| External API | None |
| AI component | Favourited/collected items feed the Personalization Engine as an explicit signal (§20, business rule) |
| Auth/authz | Authenticated traveller |
| Error handling | Standard save-failure retry; item appears only in the collection it was added to, not all collections (FR-011 acceptance criteria) |
| Testing requirement | Favourites CRUD test; collection-scoping test |
| Dependencies | F6 (POIs must exist) |
| Priority / Phase | **Should → built in Phase 1** |

### F14 — Reviews & Ratings (submit/view)
*BR-010, FR-013*

| Dimension | Detail |
|---|---|
| Frontend component | Review list on POI detail screen; post-trip rating prompt |
| Backend API | `POST /v1/reviews`, `GET /v1/pois/{id}/reviews` |
| Database tables | `reviews` |
| External API | None |
| AI component | Published review sentiment factors into future recommendation ranking (§19, §13 BR-010 rationale) |
| Auth/authz | Submission restricted to users with a **completed trip that included that place** (FR-013 business rule) |
| Error handling | Flagged-by-moderation reviews are hidden pending review, never auto-published (FR-013 exception flow); skipping review never blocks trip completion (FR-013 alt. flow) |
| Testing requirement | Review CRUD + moderation-gate test; eligibility-check test (must have completed trip) |
| Dependencies | F12 (trip completion state) |
| Priority / Phase | **Should → built in Phase 1** |

### F15 — Budget Estimate (planning-time)
*Subset of BR-018, FR-016 — tracking only, no splitting (§29.1)*

| Dimension | Detail |
|---|---|
| Frontend component | `BudgetViewScreen` (planned vs. actual, §25.1) |
| Backend API | `GET /v1/trips/{trip_id}/budget`, `POST /v1/trips/{trip_id}/expenses` |
| Database tables | `budget_expenses`, `trips.budget_planned` |
| External API | None |
| AI component | Itinerary Generation Pipeline computes the initial estimate; budget-tolerance rule enforced by the business-rule validator (§16) |
| Auth/authz | Trip owner (individual tracking only in Phase 1; group splitting is Phase 2) |
| Error handling | Malformed amount → standard input-validation error; budget tracking never blocks or auto-cancels a plan item (FR-016 business rule) |
| Testing requirement | Running-total-updates-immediately test; over-budget-notice threshold test |
| Dependencies | F3 |
| Priority / Phase | **Could, but scoped into Phase 1 as estimate-only per explicit §29.1 bullet** |

### F16 — Notifications
*Module 20*

| Dimension | Detail |
|---|---|
| Frontend component | `NotificationsCentreScreen` (in-app backup channel) + native push |
| Backend API | `GET /v1/notifications`, `PATCH /v1/notifications/{id}/read`; internal notification-dispatch service used by F7, F11, F19 |
| Database tables | `notifications`, `device_push_tokens` |
| External API | Expo Push Notification service (→ FCM/APNs) |
| AI component | None directly; content is produced by the triggering feature (arrival, disruption, expiry) |
| Auth/authz | Authenticated traveller, own notifications only |
| Error handling | Push delivery failure → queue + retry, in-app centre as guaranteed fallback channel (§24) |
| Testing requirement | Delivery-retry test; in-app fallback visibility test |
| Dependencies | F7 (arrival), F11 (expiry reminders); Expo push token registration on login |
| Priority / Phase | **Should → built in Phase 1** (cross-cutting, required by multiple Must-have features) |

### F17 — Post-Trip Feedback Capture
*BR-016, FR-018 — see Resolution Note 2, §2.1*

| Dimension | Detail |
|---|---|
| Frontend component | Short private feedback flow (per-stop thumbs up/down + free text) triggered on trip completion |
| Backend API | `POST /v1/trips/{trip_id}/feedback` |
| Database tables | `feedback_signals` |
| External API | None |
| AI component | Highest-quality personalization signal (§10.3, §20); explicit negative signal suppresses similar future suggestions, not just logged (§16 business rule) |
| Auth/authz | Trip owner/member |
| Error handling | Skipping feedback never blocks generation of the next itinerary — implicit signals used instead (FR-018 alt. flow) |
| Testing requirement | "Next itinerary reflects ≥1 piece of feedback" regression test (ties to US-018) |
| Dependencies | F12 (trip completion event) |
| Priority / Phase | **Should → built in Phase 1** (feeds the core personalization thesis from day one) |

### F18 — Analytics (Internal)
*Module 23*

| Dimension | Detail |
|---|---|
| Frontend component | None user-facing; event instrumentation embedded across all screens |
| Backend API | Internal event-ingestion middleware (no public endpoint) |
| Database tables | Analytics events land in a dedicated append-only store (see `DATABASE_SCHEMA.md` §Analytics — kept separate from operational tables) |
| External API | None (self-hosted event log; no third-party analytics SDK mandated by the PRD) |
| AI component | Feeds §37 KPI computation (itinerary success rate, recommendation acceptance rate, retention, narration engagement, memory-box adoption) |
| Auth/authz | Internal/admin role only for querying |
| Error handling | Analytics failures must never block the user-facing action they're instrumenting (fire-and-forget, non-blocking) |
| Testing requirement | Event-schema contract test; "analytics failure doesn't break primary flow" resilience test |
| Dependencies | None — instrumented alongside each feature as it's built |
| Priority / Phase | **Must — Phase 1**, cross-cutting |

---

## 4. Feature Blueprint — Phase 2 (Intelligent Travel Companion)

### F19 — Group/Collaborative Trip Planning
*BR-009, FR-012*

| Dimension | Detail |
|---|---|
| Frontend component | Invite flow (link or in-app), per-member preference form, shared itinerary view with conflict flags |
| Backend API | `POST /v1/trips/{trip_id}/invite`, `POST /v1/trips/{trip_id}/members/{user_id}/preferences` |
| Database tables | `trip_members`, `trip_preferences` |
| External API | None (invite links are internal deep links) |
| AI component | **Group Preference Reconciliation** — extends the Itinerary Generation Pipeline to merge multiple preference sets and surface trade-offs |
| Auth/authz | Organiser vs. member roles; only organiser can finalize when a member hasn't responded |
| Error handling | Non-responding member → organiser proceeds, plan clearly shows whose input was included (FR-012 exception flow); irreconcilable preferences → closest compromise + explained trade-off, never a silent pick (§16 business rule) |
| Testing requirement | Multi-user collaboration test; conflict-flag visibility test |
| Dependencies | F3, F5 |
| Priority / Phase | **Should — Phase 2** |

### F20 — Dynamic Itinerary Re-Adaptation
*BR-017, FR-014*

| Dimension | Detail |
|---|---|
| Frontend component | Adjustment-proposal card in `OnTripCompanionScreen`, with one-line reason (§25.2), accept/dismiss actions |
| Backend API | `GET /v1/trips/{trip_id}/disruptions`, `POST /v1/trips/{trip_id}/disruptions/{id}/resolve` |
| Database tables | `disruption_events` |
| External API | Weather API, Places API (closure/hours signals) |
| AI component | **Dynamic Re-Adaptation Engine** — monitors reactive triggers (§21.1: weather, closures, delay, off-route, missed activity, over-budget, schedule change, direct request) and proposes top 2–3 alternatives |
| Auth/authz | Trip owner/member |
| Error handling | No reasonable alternative exists → states so plainly rather than forcing a poor suggestion (FR-014 exception flow); nothing changes without explicit user confirmation (§16, §21.2 design principle) |
| Testing requirement | Disruption-simulation test per trigger type; dismiss-preserves-original-plan test |
| Dependencies | F7 (location), Weather API, F3 |
| Priority / Phase | **Should — Phase 2** |

### F21 — Safety / SOS Trusted-Contact Sharing
*BR-015, FR-017 — Recommended Enhancement (§12)*

| Dimension | Detail |
|---|---|
| Frontend component | `SafetyScreen` (add trusted contact, enable/disable share), SOS control (persistent on-trip UI element) |
| Backend API | `POST /v1/safety/contacts`, `POST /v1/trips/{trip_id}/share/start`, `POST /v1/safety/sos` |
| Database tables | `trusted_contacts`, `trip_location_shares`, `sos_events` |
| External API | Expo Push (SOS alert delivery), SMS/email provider for trusted-contact notification if contact isn't an app user |
| AI component | None |
| Auth/authz | Strictly opt-in per trip, never enabled by default (§27 business rule); share link is a scoped, time-limited token, not a general account credential |
| Error handling | Location unavailable at SOS trigger → last known location + timestamp sent instead of failing silently (FR-017 exception flow) |
| Testing requirement | SOS-latency test against NFR target; share-link scope test (trusted contact sees only that trip, nothing else); auto-expiry-at-trip-end test |
| Dependencies | F7 (reuses location infrastructure — low/medium complexity per §12) |
| Priority / Phase | **Should — Phase 2**, immediately after MVP |

### F22 — Weekend / Local Outing Quick Plan
*BR-011, FR-015*

| Dimension | Detail |
|---|---|
| Frontend component | `QuickPlanScreen` — time/budget/mood input, distinct entry point from "Plan a Trip" |
| Backend API | `POST /v1/quick-plans` |
| Database tables | `quick_plans`, `quick_plan_items` |
| External API | Places API, LLM provider |
| AI component | Same Personalization/Recommendation Engine as full trips, scoped down (no heritage narration, no multi-day logistics — FR-015 business rule) |
| Auth/authz | Authenticated traveller |
| Error handling | Insufficient local data for the area → states so rather than returning a low-quality generic list (FR-015 exception flow) |
| Testing requirement | 1–3-stop plan generation test; conversion-to-saved-collection test |
| Dependencies | F3, F13 |
| Priority / Phase | **Could — Phase 2** |

### F23 — Budget Tracking with Group Expense Splitting
*Extends F15 / BR-018, FR-016*

| Dimension | Detail |
|---|---|
| Frontend component | Split-entry UI on `BudgetViewScreen` for group trips |
| Backend API | `POST /v1/trips/{trip_id}/expenses` (extended with `split_with`) |
| Database tables | `budget_expenses.split_with` (jsonb) |
| External API | None |
| AI component | None |
| Auth/authz | Trip members only |
| Error handling | Same as F15 |
| Testing requirement | Split-calculation correctness test |
| Dependencies | F15, F19 |
| Priority / Phase | **Could — Phase 2** |

### F24 — Expanded Heritage POI Catalog
*Extends F8 / FR-007*

| Dimension | Detail |
|---|---|
| Frontend component | No new screens — same `HeritageNarrationScreen`, larger POI catalog |
| Backend API | No new endpoints — content-ingestion pipeline expansion |
| Database tables | `pois`, `heritage_content`, `heritage_content_embeddings` — volume growth |
| External API | Vetted tourism/heritage-body content sources (§8 Stakeholders) |
| AI component | Same RAG pipeline; content-review cadence formalized (§36) |
| Auth/authz | Content authored/verified via `admin` role tooling |
| Error handling | Same as F8 |
| Testing requirement | Golden-set suite grows with each new POI before it ships |
| Dependencies | Content-sourcing partnerships/verification effort (§41.1) |
| Priority / Phase | **Phase 2**, ongoing thereafter |

### F25 — Live Speech Translation
*Extends F10 / Module 8*

| Dimension | Detail |
|---|---|
| Frontend component | Speak/type toggle added to `PhrasebookScreen` |
| Backend API | `POST /v1/translate/speech` (thin proxy to licensed translation provider) |
| Database tables | None new (transient) |
| External API | Licensed live-translation API (not built in-house — §43.4 explicit recommendation) |
| AI component | None owned — delegated to the third-party translation provider |
| Auth/authz | Authenticated traveller |
| Error handling | Provider unavailable → falls back to F10's static phrasebook |
| Testing requirement | Provider-contract test; fallback-to-text-phrasebook test |
| Dependencies | Commercial translation API agreement |
| Priority / Phase | **Phase 2/3 per §24; listed under Phase 2 in §31** |

### F26 — Offline Heritage Access
*Recommended Enhancement, supports Module 6*

| Dimension | Detail |
|---|---|
| Frontend component | "Download for offline" action on trip/heritage screens; local content + map tile cache |
| Backend API | `GET /v1/trips/{trip_id}/offline-package` |
| Database tables | Reads from `heritage_content`, `phrasebook_entries`, `pois` — packaged, not new tables |
| External API | None (pre-fetches from own content) |
| AI component | None (pre-generated content only; no on-device inference) |
| Auth/authz | Trip owner/member |
| Error handling | Sync failure → retry, last-successful-package remains usable |
| Testing requirement | Airplane-mode full-journey test (narration + phrasebook + cached map) |
| Dependencies | F8, F10, local-storage strategy (Expo FileSystem/SQLite) |
| Priority / Phase | **Phase 2/3 — medium/high complexity (§12)** |

---

## 5. Feature Blueprint — Phase 3 (Travel Ecosystem)

### F27 — Automated Hotel/Flight Booking via Partner APIs
*BR-013*

| Dimension | Detail |
|---|---|
| Frontend component | In-app booking flow (replaces Phase 1's link-out) |
| Backend API | `POST /v1/bookings` (new service, built against the **stubbed Booking module interface established in Phase 1** — §43.7) |
| Database tables | `bookings` (new — designed but not built in Phase 1) |
| External API | Hotel/flight partner booking APIs, payments gateway |
| AI component | Smart budget-fit swap suggestions (extends Personalization Engine) |
| Auth/authz | Payment-grade security requirements activate here (PCI-DSS-aligned processor, §27) |
| Error handling | Booking failure → clear error, no partial charge, retry/alternative offered (§28); payment failure → itinerary/trip data never lost (§28) |
| Testing requirement | Full payment-flow security test suite (new for this phase), booking-availability verification test (never present unverified availability, §16) |
| Dependencies | Legal/commercial partner agreements, payments gateway integration |
| Priority / Phase | **Won't Have Yet (§30) — Phase 3** |

### F28 — Offline Mode for Maps
*Extends F26*

| Dimension | Detail |
|---|---|
| Frontend component | Offline map tile caching in `ItineraryViewScreen`/`OnTripCompanionScreen` |
| Backend API | Map-tile package endpoint |
| Database tables | None new |
| External API | Google Maps offline tile support |
| AI component | None |
| Auth/authz | Trip owner/member |
| Error handling | Same pattern as F26 |
| Testing requirement | Offline navigation continuity test |
| Dependencies | F26 |
| Priority / Phase | **Phase 3** |

---

## 6. Feature Blueprint — Phase 4 (Advanced AI Companion)

### F29 — AI-Generated Trip Recap / Shareable Memory Summaries

| Dimension | Detail |
|---|---|
| Frontend component | "Trip Recap" screen generated on trip completion, shareable export |
| Backend API | `POST /v1/trips/{trip_id}/recap/generate` |
| Database tables | Reads `memory_items`, `itinerary_items`, `feedback_signals`; writes `trip_recaps` (new) |
| External API | LLM provider (summarization) |
| AI component | Recap-generation pipeline over trip history + memory box |
| Auth/authz | Trip owner/member |
| Error handling | Generation failure → manual recap fallback (simple stats summary) |
| Testing requirement | Recap-accuracy/relevance sampling test |
| Dependencies | F11 (memory box data), F17 (feedback data) |
| Priority / Phase | **Phase 4** |

### F30 — Predictive / Proactive Recommendations

| Dimension | Detail |
|---|---|
| Frontend component | Proactive suggestion cards on `HomeScreen` |
| Backend API | `GET /v1/recommendations/proactive` |
| Database tables | Reads aggregated `feedback_signals`, `favorites`, trip history |
| External API | LLM + recommendation engine |
| AI component | Requires substantial accumulated usage data (§44) — matures from the Personalization Engine |
| Auth/authz | Authenticated traveller |
| Error handling | Insufficient data → no proactive card shown (silence is the safe default, per §21.2 design principle against over-notifying) |
| Testing requirement | Acceptance-rate tracking against KPI baseline (§37) |
| Dependencies | Sufficient production usage history |
| Priority / Phase | **Phase 3/4 (§44) — lower priority** |

### F31 — "What if?" Trip Simulation

| Dimension | Detail |
|---|---|
| Frontend component | Scenario-comparison UI in `ItineraryViewScreen` |
| Backend API | `POST /v1/trips/{trip_id}/simulate` |
| Database tables | Ephemeral — no persistence required for a simulated (non-committed) plan |
| External API | LLM provider |
| AI component | Itinerary Generation Pipeline invoked in a non-committing "preview" mode |
| Auth/authz | Trip owner |
| Error handling | Same fallback pattern as F3 |
| Testing requirement | Simulation-does-not-mutate-committed-plan test |
| Dependencies | F3 |
| Priority / Phase | **Phase 3 — lower priority (§44)** |

### F32 — Richer Model-Assisted Group Preference Reconciliation

| Dimension | Detail |
|---|---|
| Frontend component | Extends F19's conflict UI with richer trade-off explanations |
| Backend API | Extends F19's endpoints |
| Database tables | `trip_members`, `trip_preferences` |
| External API | LLM provider |
| AI component | Upgrades the rule-based reconciliation in F19 to a model-assisted negotiation |
| Auth/authz | Same as F19 |
| Error handling | Same as F19 |
| Testing requirement | Same as F19, plus quality-of-explanation sampling |
| Dependencies | F19, sufficient group-trip usage data |
| Priority / Phase | **Phase 4** |

---

## 7. Cross-Cutting Non-Functional Requirements (apply to every feature above)

| Category | Target (Proposed / TBC per PRD §15 unless stated) |
|---|---|
| Performance | Itinerary generation 8–12s; chat replies 3–5s |
| Availability | 99.5% uptime for core services |
| Reliability | Graceful degradation on any dependency failure (LLM/Maps/Weather) — never a hard crash |
| Security | TLS in transit; encryption at rest for location history and photos; rate limiting on all public endpoints (esp. AI endpoints, for cost/abuse control) |
| Privacy | Explicit, granular, per-trip consent for location and camera; minimal retention (location: active-trip only; memory box: 12 months, never silent deletion) |
| Usability | Onboarding completable in <6 screens |
| Accessibility | WCAG 2.1 AA aspiration (TBC) |
| Observability | Centralized logging, tracing, alerting on every service boundary |
| Data integrity | Input validation + idempotent writes on all mutating endpoints |
| Disaster recovery | Automated daily backups minimum; RPO/RTO TBC |

Full detail: `DATABASE_SCHEMA.md` (data model + retention + RLS), `API_SPECIFICATION.md` (endpoint contracts + error codes), `AI_ARCHITECTURE.md` (RAG/guardrails/evaluation), `MOBILE_ARCHITECTURE.md` (client architecture), `DEPLOYMENT_PLAN.md` (environments/CI-CD/monitoring), `TESTING_PLAN.md` (test strategy per layer).

---

## 8. Build Sequencing (first increment)

Recommended sprint-zero → sprint-N order, respecting the dependency chains stated in each feature's "Dependencies" row above:

1. **Infra bootstrap:** Supabase project (Auth + Postgres + pgvector + Storage), FastAPI skeleton + CI, Expo app skeleton + EAS config.
2. **F1 Auth → F2 Onboarding** (nothing else is testable end-to-end without a real user).
3. **F6 Maps & Navigation** (POI data model needed by almost everything downstream).
4. **F3 Itinerary Generation → F4 Trip Ideas → F5 Conversational Modification** (the core loop).
5. **F12 Trip Management, F15 Budget Estimate** (thin wrappers around the trip entity already created).
6. **F7 Location Companion → F16 Notifications** (on-trip loop).
7. **F8 Heritage Narration → F9 Visual Q&A** (requires curated content ingestion to have started in parallel from sprint 1 — this is a content-pipeline dependency, not just an engineering one, per §41.1).
8. **F10 Phrasebook, F11 Memory Box, F13 Collections/Favourites, F14 Reviews, F17 Feedback** (parallelizable across the team once the core loop is stable).
9. **F18 Analytics** — instrumented alongside every step above, not as a discrete late step.
10. Phase 2 features begin only once Phase 1 acceptance criteria (§14, §17) and the golden-set AI evaluation bar (§34) are met, per the SDLC Phase 7 (Testing) exit criteria in the PRD (§32).
