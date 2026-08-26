# API Specification
## FastAPI REST API — AI Personalized Tourist Guide (TC-SO1)

Companion to `IMPLEMENTATION_BLUEPRINT.md` and `DATABASE_SCHEMA.md`. Endpoint groups and table references are consistent across all three documents.

**Phase 3 conflict resolution (H1, `ARCHITECTURE_REVIEW.md`):** §2 below previously described `POST /auth/session/bootstrap` as the mechanism that "provisions" the `profiles` row. Phase 2 implemented the actual profile-creation mechanism as a database trigger (`handle_new_user()` on `auth.users` insert — see `DATABASE_SCHEMA.md` §3), not an API call. This was a real conflict between this document and what got built: the trigger runs the instant Supabase Auth creates the `auth.users` row, before the mobile client could ever call a bootstrap endpoint. §2 is updated below to describe `/auth/session/bootstrap` accurately as an idempotent **load-or-defensive-create** call — it reads the profile the trigger already created; the create path only fires if the trigger somehow didn't run, which should not happen in normal operation but is handled rather than assumed away. This is not a product requirement change (FR-002's "no partial account on denied consent" still holds — the trigger only fires after Supabase Auth confirms a real user, same guarantee, enforced one layer earlier and more reliably than an API call could).

---

## 1. Conventions

| | |
|---|---|
| Base URL | `https://api.<domain>/v1` |
| Format | JSON request/response bodies; `Content-Type: application/json` except file upload endpoints (`multipart/form-data`) |
| Auth header | `Authorization: Bearer <supabase_jwt>` on every endpoint except `POST /auth/session/bootstrap` (which itself requires a just-issued Supabase session token) and the public SOS-share viewer route |
| Versioning | URL-prefixed (`/v1`); breaking changes ship as `/v2` alongside `/v1` during a deprecation window |
| Pagination | Cursor-based: `?limit=20&cursor=<opaque>` → response includes `next_cursor` (null when exhausted) |
| Idempotency | All `POST` endpoints that create a resource accept an optional `Idempotency-Key` header; the server stores the key→response mapping for 24h to satisfy the NFR "idempotent write operations on all mutating endpoints" (PRD §15) |
| Rate limiting | Per-user token bucket; **AI endpoints (chat, itinerary generation, photo Q&A) are limited more strictly** than CRUD endpoints, per PRD §27 ("rate limiting on all public endpoints, particularly AI endpoints — cost and abuse control"). Defaults: 60 req/min general, 10 req/min AI-generation endpoints (Proposed Target, tune post-launch) |
| Errors | Standard envelope, see §2 |

### Standard success envelope

```json
{ "data": { ... }, "meta": { "next_cursor": null } }
```

### Standard error envelope

```json
{
  "error": {
    "code": "BUDGET_EXCEEDED",
    "message": "Estimated itinerary cost exceeds stated budget by more than 10%.",
    "details": { "estimated": 18500, "budget": 15000, "tolerance_pct": 10 }
  }
}
```

| HTTP status | Meaning |
|---|---|
| 400 | Validation error (malformed input) |
| 401 | Missing/invalid/expired auth token |
| 403 | Authenticated but not authorized for this resource (RLS-equivalent check failed) |
| 404 | Resource not found or not visible to this user |
| 409 | Conflict (e.g. duplicate idempotency key with different payload, concurrent-edit conflict) |
| 422 | Business-rule violation (e.g. `BUDGET_EXCEEDED`, `OUTSIDE_OPENING_HOURS`) — always includes a human-readable `message` per PRD's "explain why, offer alternative" pattern (§16, FR-004) |
| 429 | Rate limit exceeded |
| 502/503 | Upstream dependency (LLM, Maps, Weather) unavailable — response body indicates whether a fallback was served instead (`meta.degraded_mode: true`) rather than a hard failure, per §24 |

---

## 2. Auth & Session
*Backend: Phase 3 (Authentication, Authorization & User Identity) · DB: `profiles`*

Every endpoint below derives identity **exclusively** from the verified Supabase JWT (`Authorization: Bearer <access_token>`) via the `get_current_user()` dependency — none accepts a user id as a path/query/body parameter. A request with no token, an expired token, a malformed token, or a token with an invalid signature/audience is rejected with `401` before any handler code runs.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/auth/session/bootstrap` | Bearer | **Idempotent load-or-defensive-create.** The `profiles` row is actually created by the `handle_new_user()` database trigger the instant Supabase Auth creates the `auth.users` row (`DATABASE_SCHEMA.md` §3) — not by this endpoint. This call reads that row; if (and only if, which should not happen in normal operation) the trigger hasn't run yet, it creates the row defensively rather than erroring. Client calls this once right after a session is established, before navigating past sign-in. |
| `GET` | `/auth/me` | Bearer | Returns the caller's own `profiles` row + `onboarding_completed_at` flag. The Phase 3 proof-of-concept protected endpoint. |
| `POST` | `/auth/logout` | Bearer | Calls Supabase Auth's admin sign-out for the caller's session, revoking their **refresh token** server-side (defense-in-depth beyond the client clearing its local session). Honest security property, stated plainly rather than overclaimed: this does not instantly invalidate the **access token** already issued — JWTs are stateless and remain cryptographically valid until their own (short, ~1h) expiry regardless of logout, exactly like any standard JWT-based system. What logout guarantees is that no *new* access token can be minted from that refresh token afterward. |
| `POST` | `/auth/account/delete-request` | Bearer | **Deferred, not implemented this phase.** Documented here for completeness (matches `DEPLOYMENT_PLAN.md` §6's workflow) but is a data-lifecycle feature (audit logging, a multi-step deletion workflow) distinct from core identity — out of Phase 3's scope, which is authentication/authorization/identity only. |

**Response — `GET /auth/me`**
```json
{ "data": { "id": "uuid", "display_name": "Meera", "role": "traveller",
  "onboarding_completed_at": null, "home_region": "Tamil Nadu" } }
```

**Response — unauthenticated/invalid token (any endpoint above) — `401`**
```json
{ "error": { "code": "UNAUTHORIZED", "message": "Authentication required." } }
```

---

## 3. Onboarding
*Backend: F2 · DB: `interests`, `profile_interests`, `profiles`*

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/onboarding/interests` | Bearer | List curated interest tags to render the selection UI |
| `POST` | `/onboarding/responses` | Bearer | Submit interests + travel_style + budget_bracket + pace |
| `GET` | `/onboarding/status` | Bearer | Whether onboarding is complete (drives skip-logic) |

**Request — `POST /onboarding/responses`**
```json
{ "interest_ids": [1, 4, 7], "travel_style": "balanced", "budget_bracket": "mid", "pace": "relaxed" }
```
Save failure never blocks the user (FR-003 exception flow) — the endpoint returns `202 Accepted` with `meta.saved: false` and retries server-side in the background rather than surfacing a hard error to the client.

---

## 4. Trips & Itinerary
*Backend: F3, F4, F5, F12 · DB: `trips`, `itinerary_days`, `itinerary_items`, `trip_raw_notes`*

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/trips` | Bearer | Create a draft trip (title, destination, dates, budget) |
| `GET` | `/trips` | Bearer | List caller's trips, grouped by `status` (US-020) |
| `GET` | `/trips/{trip_id}` | Bearer, member | Full trip detail incl. itinerary |
| `PATCH` | `/trips/{trip_id}` | Bearer, owner | Update status/dates/budget |
| `DELETE` | `/trips/{trip_id}` | Bearer, owner | Soft-delete (`deleted_at`); memory items untouched (§28) |
| `POST` | `/trips/{trip_id}/notes` | Bearer, member | Submit free-text trip ideas (FR-005) |
| `POST` | `/trips/{trip_id}/itinerary/generate` | Bearer, member | Trigger AI itinerary generation (FR-001) |
| `POST` | `/trips/{trip_id}/itinerary/modify` | Bearer, member | Conversational modification of an existing itinerary (FR-004) |
| `GET` | `/trips/{trip_id}/itinerary` | Bearer, member | Current itinerary (days + items) |
| `PATCH` | `/trips/{trip_id}/itinerary/items/{item_id}` | Bearer, member | Manual edit/reorder/status change |

**Request — `POST /trips/{trip_id}/itinerary/generate`**
```json
{ "interests": ["heritage","food"], "budget": 15000, "time_window": {"start":"2026-10-10","end":"2026-10-13"},
  "destination": "Agra, India", "use_own_ideas": true }
```

**Response (success)**
```json
{ "data": { "trip_id": "uuid", "generation_status": "succeeded", "summary": "A sunrise Taj Mahal visit, ...",
  "days": [ { "day_number": 1, "date": "2026-10-10", "items": [
    { "id": "uuid", "poi_id": "uuid", "poi_name": "Taj Mahal", "planned_start": "06:00",
      "estimated_duration_min": 150, "estimated_cost": 1100, "verify_on_arrival": false,
      "weather_flag": false, "weather_alternative_suggestion": null } ] } ],
  "budget_summary": { "estimated_total": 14200, "planned_budget": 15000, "over_budget": false, "tolerance_pct": 10 },
  "conflicts": [] } }
```

**Response (AI layer failure → fallback, FR-001 exception flow)**
```json
{ "data": { "trip_id": "uuid", "generation_status": "fallback_used", "summary": "Here's a starter plan for Agra, India.", "days": [ /* real curated-POI schedule, no AI call */ ] },
  "meta": { "degraded_mode": true, "message": "Live generation is temporarily unavailable — showing a curated starter plan." } }
```

**Response (clarification needed, FR-001 alt. flow) — `422`**
```json
{ "error": { "code": "CLARIFICATION_NEEDED", "message": "What's your rough budget for this trip?",
  "details": { "missing_fields": ["budget"] } } }
```

**Business-rule handling, as actually implemented (Phase 6, documented per CLAUDE.md §13):** `BUDGET_EXCEEDED` is **always an advisory flag** (`budget_summary.over_budget`), never a hard rejection of the whole plan — F15's own rule that budget tracking "never blocks or auto-cancels a plan item" is read here as applying to itinerary generation as a whole. `OUTSIDE_OPENING_HOURS` is implemented as presence-of-hours-data (`verify_on_arrival`), not fine-grained hour-range conflict detection — `pois.opening_hours` has no single documented schema precise enough to parse reliably (curated seed data and Google Places' raw format differ); a known, bounded limitation, not a silent gap. `UNREALISTIC_TRAVEL_DISTANCE`-class conflicts are returned as advisory `conflicts[]` strings on generation, and as a hard-rejected diff (with the pre-existing schedule left untouched) on `POST .../itinerary/modify` specifically, since F5's own diff must be validated as "allowed" before being applied.

---

## 5. POIs & Maps
*Backend: F6 · DB: `pois`*

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/pois/search` | Bearer | Query by text/category/bounding box; backend-cached proxy over Google Places, never exposes the raw Maps API key to the client |
| `GET` | `/pois/{poi_id}` | Bearer | POI detail |
| `GET` | `/pois/nearby` | Bearer | `?lat&lng&radius_m&category` — `ST_DWithin` query against `pois.location` |

Map-tile load failures are a client-side concern (degrade to list view, §24) — no server endpoint needed for that fallback.

---

## 6. Location & On-Trip Companion
*Backend: F7 · DB: `location_pings`, `itinerary_items`*

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/trips/{trip_id}/location/ping` | Bearer, member, **explicit per-trip location consent required** | Submit a location sample; server checks against planned stops' geofences and returns any arrival event + nearby recommendations in the same response (avoids a second round trip from a battery-constrained client) |
| `GET` | `/trips/{trip_id}/nearby` | Bearer, member | On-demand nearby recommendations without submitting a new ping |
| `POST` | `/trips/{trip_id}/location/manual` | Bearer, member | Manual "I'm at ___" fallback when GPS permission is denied (FR-006 exception flow) |

**Request — `POST /trips/{trip_id}/location/ping`**
```json
{ "lat": 27.1751, "lng": 78.0421, "recorded_at": "2026-10-10T06:02:11Z" }
```
**Response**
```json
{ "data": { "arrival_event": { "itinerary_item_id": "uuid", "poi_name": "Taj Mahal" },
  "nearby": [ { "poi_id": "uuid", "name": "Mehtab Bagh", "distance_m": 850 } ] } }
```
`403` returned if the trip has no active location-sharing consent recorded — the endpoint refuses to accept a location write rather than silently accepting it (BR-014).

---

## 6b. Dynamic Itinerary Re-Adaptation (Phase 8)
*Backend: F20 · DB: `disruption_events` · AI_ARCHITECTURE.md §8*

**Documented resolution of ARCHITECTURE_REVIEW.md H2** (`disruption_events` had two contradictory API surfaces across documents — this document's own traceability table said "via notifications," `IMPLEMENTATION_BLUEPRINT.md` F20 specified dedicated endpoints): the Blueprint's dedicated endpoints below are authoritative, per H2's own recommended resolution. The vaguer "via notifications" description is retired.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/trips/{trip_id}/disruptions` | Bearer, member | List all disruption events for the trip (proposed/accepted/dismissed) |
| `POST` | `/trips/{trip_id}/disruptions/check` | Bearer, member | Manually trigger a real check against current conditions (weather is the one genuinely auto-detected trigger this phase — see `app/services/disruption_service.py`'s module docstring for the other schema-supported trigger types not yet wired to a live signal) |
| `POST` | `/trips/{trip_id}/disruptions/{event_id}/resolve` | Bearer, member | `{ "decision": "accept" \| "dismiss", "alternative_index"? }` — nothing is ever applied to the itinerary until this is called with `"accept"` (§16, §21.2) |

Real, live-throttled detection also runs opportunistically inside `POST /trips/{id}/location/ping` (F7) — no `pg_cron`/scheduler infrastructure exists yet in this environment (same class of gap as the still-unbuilt `location_pings` retention job), so this is the real, working substitute for a true scheduled cadence, documented rather than silently assumed.

**Response — `GET /trips/{trip_id}/disruptions`**
```json
{ "data": [ { "id": "uuid", "trip_id": "uuid", "itinerary_item_id": "uuid", "trigger_type": "weather",
  "detected_at": "2026-10-10T05:00:00Z",
  "proposal": { "reason": "Adverse weather is forecast for Taj Mahal on 2026-10-10.",
    "alternatives": [ { "poi_id": "uuid", "poi_name": "Agra Fort", "lat": 27.18, "lng": 78.02 } ] },
  "status": "proposed", "resolved_at": null } ] }
```

---

## 6c. Offline Heritage Access (Phase 8)
*Backend: F26 · Reads: `heritage_content`, `phrasebook_entries`, `pois` (packaged, no new tables)*

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/trips/{trip_id}/offline-package` | Bearer, member | Real bundle of the trip's own itinerary POIs, their published heritage overview content, and the destination's curated phrasebook — the mobile client persists this locally (`expo-file-system`) for read-only offline use |

Map-tile offline caching is explicitly out of scope (documented decision, `app/services/offline_service.py`'s module docstring) — no verifiable first-party `react-native-maps` offline-tile API exists to build against.

---

## 7. Heritage Narration (RAG)
*Backend: F8 · DB: `pois`, `heritage_content`, `heritage_content_embeddings`*

**Phase 6 implementation note (documented per CLAUDE.md §13):** this section originally sketched a `sections` array response and a separate `POST /heritage/{poi_id}/report-missing` endpoint. As actually built, the narration endpoint returns one **composed, grounded narration string** (the LLM synthesizes the retrieved chunks into readable prose, per `AI_ARCHITECTURE.md` §5.2 — returning raw un-composed chunks would push grounding-contract enforcement onto the client) plus a `sources` list naming which curated sections were used. `report-missing` was not built — a 404 `POI_NOT_COVERED` already surfaces the gap to the traveller; a dedicated logging endpoint was judged genuinely separate scope (an admin/content-ops feature, not core RAG) and can be added later without any change to this contract.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/heritage/{poi_id}/narration` | Bearer | `?layer=overview\|deep&section=` — returns RAG-grounded narration; see `AI_ARCHITECTURE.md` §5.2 for retrieval logic |

**Response (supported POI)**
```json
{ "data": { "poi_id": "uuid", "poi_name": "Taj Mahal", "layer": "overview",
  "narration": "The Taj Mahal is an ivory-white marble mausoleum...",
  "confidence": "high", "sources": ["Overview"] } }
```
**Response (unsupported POI) — `404`**
```json
{ "error": { "code": "POI_NOT_COVERED", "message": "We don't have verified heritage information for this place yet." } }
```
**Response (AI provider not configured/unavailable) — `503`**
```json
{ "error": { "code": "UPSTREAM_UNAVAILABLE", "message": "Heritage narration is temporarily unavailable — the AI provider is not configured." } }
```

---

## 8. Visual Q&A (Photo-Based)
*Backend: F9 · DB: `heritage_content_embeddings`, `ai_messages`*

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/heritage/{poi_id}/photo-qa` | Bearer | `multipart/form-data`: `image` file + `question` text |

**Response**
```json
{ "data": { "poi_id": "uuid",
  "answer": "This carved lattice is a jali screen — pierced marble used for ventilation and light...",
  "confidence": "high", "grounded": true } }
```
**Response (low confidence, FR-008 business rule — still `200`, always visibly flagged, never suppressed)**
```json
{ "data": { "poi_id": "uuid",
  "answer": "I can't confidently identify this detail from the photo. It may be a later restoration addition — worth asking on-site staff.",
  "confidence": "low", "grounded": false } }
```
**Response (unusable image) — `422`**
```json
{ "error": { "code": "IMAGE_UNUSABLE", "message": "That image format isn't supported — please retake the photo (JPEG, PNG, or WebP)." } }
```

---

## 9. Phrasebook & Translation
*Backend: F10 (Phase 1 curated + Phase 6 dynamic extension), F25 speech (Phase 6) · DB: `phrasebook_entries`*

**Phase 6 implementation note (`ARCHITECTURE_REVIEW.md` M11):** the curated phrasebook (`GET /phrasebook/{region}`) covers fixed, pre-authored phrases only — M11 flagged that arbitrary typed-phrase translation had no endpoint. `POST /translate/text` (new this phase) closes that gap with a real Gemini call, not a lookup table — any language Gemini supports, not a hardcoded enum. `POST /translate/speech` was originally specified as proxying a separate "licensed live-translation provider" — since Gemini has native audio-input understanding, this project's `LLMGateway` handles it directly instead (one fewer vendor, `AI_ARCHITECTURE.md` §1's whole point). **Honesty boundary:** this is batch audio-clip translation (record → upload → transcribe+translate once), not a continuous real-time voice stream — see `speech_translation_service.py`'s module docstring.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/phrasebook/{region}` | Bearer | `?language=&category=` |
| `POST` | `/trips/{trip_id}/phrasebook/download` | Bearer, member | Bundles relevant entries for offline caching (ties to F26) |
| `POST` | `/translate/text` | Bearer | `{ "text": "...", "target_language": "Hindi" }` — arbitrary-phrase translation, real Gemini call |
| `POST` | `/translate/speech` | Bearer | `multipart/form-data`: `audio` file + `target_language` — batch transcribe + translate |

**Response — `POST /translate/text`**
```json
{ "data": { "original_text": "Where is the nearest railway station?", "target_language": "Hindi",
  "translated_text": "निकटतम रेलवे स्टेशन कहाँ है?", "transliteration": "Nikatatam railway station kahaan hai?",
  "note": null, "recognized_language": true } }
```
**Response — `POST /translate/speech`**
```json
{ "data": { "transcribed_text": "Where is the nearest railway station?", "target_language": "Hindi",
  "translated_text": "निकटतम रेलवे स्टेशन कहाँ है?", "transliteration": "Nikatatam railway station kahaan hai?", "note": null } }
```
**Response (AI provider not configured/unavailable) — `503`**
```json
{ "error": { "code": "UPSTREAM_UNAVAILABLE", "message": "Translation is temporarily unavailable — the AI provider is not configured." } }
```
**Response (unusable audio) — `422`**
```json
{ "error": { "code": "AUDIO_UNUSABLE", "message": "That audio format isn't supported." } }
```

---

## 10. Trip Memory Box
*Backend: F11 · DB: `memory_items`, Supabase Storage*

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/trips/{trip_id}/memory-items` | Bearer, member | `multipart/form-data` upload (photo/video) or JSON note; returns a Storage signed upload URL flow (client uploads directly to Storage, backend records metadata) to avoid proxying large binaries through the API |
| `GET` | `/trips/{trip_id}/memory-items` | Bearer, member | Paginated gallery |
| `GET` | `/trips/{trip_id}/memory-items/export` | Bearer, member | Returns a zipped export job (async — see `GET .../export/{job_id}`) |
| `DELETE` | `/trips/{trip_id}/memory-items/{item_id}` | Bearer, member | Explicit user deletion only — the retention job never calls this internally (§43.3) |

Upload failure handling: if the Storage `PUT` fails after the backend issued a signed URL, the client retries against the same signed URL (idempotent); the metadata row is only created after a confirmed successful upload, so there is never an orphaned "ghost" memory item (FR-010 exception flow: "retries or clearly reports failure... never silently dropped").

---

## 11. Collections & Favourites
*Backend: F13 · DB: `favorites`, `collections`, `collection_items`*

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/favorites` | Bearer | `{ "poi_id": "uuid" }` |
| `DELETE` | `/favorites/{poi_id}` | Bearer | Un-favourite |
| `POST` | `/collections` | Bearer | `{ "name": "Food to try" }` |
| `GET` | `/collections` | Bearer | List caller's collections |
| `POST` | `/collections/{collection_id}/items` | Bearer, owner | `{ "poi_id": "uuid" }` |

---

## 12. Reviews
*Backend: F14 · DB: `reviews`*

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/pois/{poi_id}/reviews` | Bearer | Published reviews only, paginated |
| `POST` | `/reviews` | Bearer | `{ "poi_id", "trip_id", "rating", "review_text" }` — server-side check mirrors the DB `reviews_insert_own` policy (must have a `completed` trip that included this POI); returns `403 REVIEW_NOT_ELIGIBLE` otherwise |

New reviews are created with `status = 'pending'` and excluded from `GET /pois/{poi_id}/reviews` until an admin-moderation endpoint (§20) publishes them.

---

## 13. Group Trips (Phase 2)
*Backend: F19 · DB: `trip_members`, `trip_preferences`, `trip_invites` (Phase 8 addition)*

**Documented schema decision (Phase 8):** `trip_members`' primary key requires a known `user_id`, but an invite link/email is issued before that identity is known. A new `trip_invites` table (migration `20260828120001`) holds the pending, redeemable token; the real `trip_members` row is only ever created — directly as `invite_status='accepted'` — at the moment `POST /trips/invite/{token}/accept` succeeds. See `app/repositories/group_repository.py`'s module docstring.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/trips/{trip_id}/invite` | Bearer, owner | `{ "method": "link" }` or `{ "method": "email", "email": "..." }` — returns a real, redeemable `token`/`invite_url`; no email is actually sent (no provider was ever named for this — the Blueprint itself lists "External API: None" for F19) |
| `POST` | `/trips/invite/{invite_token}/accept` | Bearer | Joins the inviting trip as a member |
| `POST` | `/trips/{trip_id}/members/{user_id}/preferences` | Bearer, self (`user_id` must equal the caller) | Submit own interests/budget/constraints |
| `GET` | `/trips/{trip_id}/members` | Bearer, member | List the trip's members and their invite status (Phase 8 addition — the frontend's shared member list needs this) |
| `POST` | `/trips/{trip_id}/itinerary/reconcile` | Bearer, owner | Regenerate itinerary from all submitted member preferences; response includes a `conflicts[]` array with the trade-off explanation for each (FR-012 business rule) |

**Documented resolution of ARCHITECTURE_REVIEW.md H5** ("edit rights" language had no PRD basis and no RLS implementation): any accepted trip member can propose/apply itinerary changes — matches the existing permissive `is_trip_accessible()`/RLS behavior every F3/F4/F5 endpoint already relies on. No differentiated permission tier was added.

---

## 14. Budget
*Backend: F15, F23 · DB: `budget_expenses`*

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/trips/{trip_id}/budget` | Bearer, member | Planned vs. actual summary |
| `POST` | `/trips/{trip_id}/expenses` | Bearer, member | `{ "category", "amount", "currency", "split_with"? }` |

Over-budget notice is computed server-side and surfaced via a `notifications` row + included in the response `meta.over_budget: true`, never blocks the write (FR-016 business rule). `split_with` (Phase 8, F23) is validated server-side against real trip membership (`SPLIT_WITH_NON_MEMBER` if any named `user_id` isn't the owner or an accepted member); `GET /trips/{id}/budget`'s response additionally includes a computed `per_member_owed: { [user_id]: amount }` breakdown, summed across every expense that carries a `split_with`.

---

## 15. Notifications & Devices
*Backend: F16 · DB: `notifications`, `device_push_tokens`*

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/notifications` | Bearer | Paginated, newest first |
| `PATCH` | `/notifications/{id}/read` | Bearer | Mark read |
| `POST` | `/devices/push-token` | Bearer | Register/refresh an Expo push token on login |
| `DELETE` | `/devices/push-token` | Bearer | Unregister on logout |

---

## 16. Safety / SOS (Phase 2)
*Backend: F21 · DB: `trusted_contacts`, `trip_location_shares`, `sos_events`*

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/safety/contacts` | Bearer | Add a trusted contact |
| `GET` | `/safety/contacts` | Bearer | List |
| `POST` | `/trips/{trip_id}/share/start` | Bearer, member, **explicit opt-in per trip** | Creates `trip_location_shares` row, returns a share URL |
| `POST` | `/trips/{trip_id}/share/stop` | Bearer, member | Deactivates sharing immediately |
| `GET` | `/share/{share_token}` | **None (public, token-scoped)** | Trusted-contact viewer — read-only, live location for *that trip only*, served via service-role query validated against `share_token` + `expires_at`, never a generic authenticated API |
| `POST` | `/safety/sos` | Bearer | Triggers an SOS event; notifies all trusted contacts for the active trip via push/SMS/email |

---

## 17. Feedback
*Backend: F17 · DB: `feedback_signals`*

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/trips/{trip_id}/feedback` | Bearer, member | Per-stop thumbs up/down + free text, triggered on trip completion |

An `explicit_correction` signal type immediately writes to `personalization_profile` server-side and is guaranteed to suppress similar future suggestions (§16 business rule) — this is enforced in the Personalization Engine, not left to eventual-consistency batch processing.

---

## 18. Quick Plans (Phase 2)
*Backend: F22 · DB: `quick_plans`, `quick_plan_items`*

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/quick-plans` | Bearer | `{ "time_available_min", "budget"?, "occasion"?, "lat"?, "lng"? }` → 1–3 stop plan. `lat`/`lng` (Phase 8 addition, not in the original request shape sketched here) scope candidates to the traveller's current position; when omitted, falls back to `profiles.home_region` text search. Neither present → `422 NOT_ENOUGH_LOCAL_DATA` (FR-015 exception flow — states so rather than returning a low-quality generic list) |
| `POST` | `/quick-plans/{id}/save-to-collection` | Bearer | Converts a quick plan into a saved collection |

---

## 19. Admin (Content & Moderation)
*Backend: F8/F24 content pipeline, F14 review moderation · Auth: `role = 'admin'` only*

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/admin/pois` | Create/curate a POI |
| `POST` | `/admin/heritage-content` | Create a heritage content section (starts `is_published = false`) |
| `PATCH` | `/admin/heritage-content/{id}/publish` | Verifies + publishes; triggers embedding generation (`AI_ARCHITECTURE.md` §Ingestion) |
| `GET` | `/admin/reviews/pending` | Moderation queue |
| `PATCH` | `/admin/reviews/{id}/moderate` | `{ "decision": "publish" \| "reject" }` |
| `GET` | `/admin/analytics/kpis` | KPI dashboard data feed (§37 metrics) |

---

## 20. Bookings (Phase 3 — stubbed interface only)
*Backend: F27 · DB: `bookings`*

| Method | Path | Status |
|---|---|---|
| `POST` | `/bookings` | **Not implemented pre-Phase-3.** Route reserved and documented now (contract only) so downstream modules can be built against a stable interface without a later rebuild, per BR-013. Returns `501 NOT_IMPLEMENTED` until Phase 3. |

---

## 21. Endpoint-to-Requirement Traceability

| FR | Endpoint(s) |
|---|---|
| FR-001 | `POST /trips/{id}/itinerary/generate` |
| FR-002 | `POST /auth/session/bootstrap`, `GET /auth/me` |
| FR-003 | `POST /onboarding/responses` |
| FR-004 | `POST /trips/{id}/itinerary/modify` |
| FR-005 | `POST /trips/{id}/notes` |
| FR-006 | `POST /trips/{id}/location/ping`, `POST .../location/manual` |
| FR-007 | `GET /heritage/{poi_id}/narration` |
| FR-008 | `POST /heritage/{poi_id}/photo-qa` |
| FR-009 | `GET /phrasebook/{region}` |
| FR-010 | `POST/GET /trips/{id}/memory-items` |
| FR-011 | `POST /favorites`, `POST /collections` |
| FR-012 | `POST /trips/{id}/invite`, `.../reconcile` |
| FR-013 | `POST /reviews`, `GET /pois/{id}/reviews` |
| FR-014 | `GET /trips/{id}/disruptions`, `POST /trips/{id}/disruptions/check`, `POST .../disruptions/{id}/resolve` (Phase 8 — resolves ARCHITECTURE_REVIEW.md H2 in favor of the Blueprint's dedicated endpoints; see §6b) |
| FR-015 | `POST /quick-plans` |
| FR-016 | `POST /trips/{id}/expenses`, `GET /trips/{id}/budget` |
| FR-017 | `POST /safety/sos`, `POST /trips/{id}/share/start` |
| FR-018 | `POST /trips/{id}/feedback` |

This table is the FR ↔ endpoint half of the PRD's Section 42 traceability matrix; the FR ↔ table half lives in `DATABASE_SCHEMA.md`, and the FR ↔ test-scenario half lives in `TESTING_PLAN.md`.
