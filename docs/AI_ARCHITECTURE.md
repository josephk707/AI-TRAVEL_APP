# AI Architecture
## AI / RAG Services Layer — AI Personalized Tourist Guide (TC-SO1)

Per PRD Section 19: *"AI is the core of this product, not a bolt-on feature."* This document details the AI/Recommendation layer that sits between the FastAPI Business Logic Layer and the External APIs layer in the target architecture (`IMPLEMENTATION_BLUEPRINT.md` §1). All AI work happens as **orchestration inside the FastAPI backend** — hosted models are called over HTTPS; nothing is self-hosted or trained in-house, per PRD §26.4 and §39 (Assumptions).

---

## 1. LLM Gateway — Provider Abstraction

**Phase 6 implementation note:** the PRD deliberately left the LLM vendor unnamed; this project's chosen provider is **Google Gemini** (`app/services/ai/gemini_adapter.py`, the sole call site for the `google-genai` SDK). Text/structured generation uses `gemini-2.5-flash` (fast, cheap — itinerary generation, idea extraction, conversational modification, translation) or `gemini-2.5-pro` (stronger reasoning, used for plain unstructured `complete()` calls); embeddings use `gemini-embedding-001` truncated to 1536 dimensions via `output_dimensionality`, matching the `vector(1536)` columns already fixed in `DATABASE_SCHEMA.md`. All three are config values (`Settings.gemini_text_model`/`gemini_reasoning_model`/`gemini_embedding_model`), not hardcoded, per this section's own "config value, not architectural commitment" principle below. `LLM_PROVIDER=gemini` is the only value currently supported; a second adapter would only need to implement the same `LLMGateway` protocol.

The PRD deliberately does not name an LLM vendor (§26.4, §41.2 lists "LLM/AI provider" as an external dependency, TBC). This is implemented as a single internal interface so the concrete provider is a config value, not an architectural commitment:

```
services/ai/llm_gateway.py
  class LLMGateway(Protocol):
      def complete(self, messages, *, response_schema=None, max_tokens, temperature) -> LLMResponse
      def embed(self, texts: list[str]) -> list[list[float]]
      def complete_multimodal(self, messages_with_images, ...) -> LLMResponse
```

Concrete adapters (`AnthropicAdapter`, `OpenAIAdapter`, etc.) implement this interface; selection is a single environment variable (`LLM_PROVIDER`). Every AI-facing service in this document (itinerary generation, narration, Q&A) is written against `LLMGateway`, never against a vendor SDK directly. This directly serves:

- **§24's fallback requirement** — a provider outage can fail over to a secondary adapter or to cached/curated content without touching call sites.
- **§38's cost-overrun risk** — model/provider swaps for cost reasons don't require a rewrite.
- **§27's data-protection requirement** — "user data is not used to train third-party foundation models without explicit consent" is enforced at the gateway layer (request options set `train_on_data: false` / equivalent for every adapter that supports it, verified per-provider before enabling it in production).

**Embedding model:** a single, fixed embedding model is used for all of `heritage_content_embeddings` and `personalization_profile.taste_embedding` (mixing embedding models in one vector column breaks cosine-similarity comparisons). Default assumption: a 1536-dimension embedding model (matches the `vector(1536)` column in `DATABASE_SCHEMA.md`) — if a different model/dimension is selected during setup, the migration and this document must be updated together, since **re-embedding the entire heritage corpus is required on any embedding-model change.**

---

## 2. Itinerary Generation Pipeline (FR-001)

**Trigger:** `POST /trips/{trip_id}/itinerary/generate`

```
1. Assemble context
   - profiles + profile_interests (explicit onboarding signal)
   - personalization_profile.preference_weights (learned signal, if it exists — cold-start: absent for new users)
   - request payload: interests, budget, time_window, destination
   - trip_raw_notes.extracted_places (if the user pasted their own ideas — see §3 Idea Extraction, runs first)
   - favorites / collections for this user (explicit signal, §20 business rule)
2. Candidate POI retrieval (Hybrid Recommendation Engine, §5)
   - rule-based filter: budget fit, opening hours, geographic reachability within the time window (§16)
   - embedding similarity: free-text interests → POI/heritage-content embedding space
   - behavioral boost: past feedback_signals, review sentiment on candidate POIs
3. LLM composition
   - LLMGateway.complete() with a structured-output schema (day-by-day items, times, cost estimates)
   - system prompt fixes tone (companion, not travel-agent-formal — §5.3) and forbids inventing POIs not present in the candidate set from step 2 (prevents hallucinated venues)
4. Business-rule validation (deterministic, NOT delegated to the LLM;
   `app/services/business_rules.py`)
   - total cost vs. budget (>10% tolerance → flag, §16) — always advisory, never blocks the plan
   - opening-hours conflicts → item marked verify_on_arrival if hours unknown
   - travel-time buffers between geographically distant stops
   - itinerary items must not overlap
   - **outdoor-category items checked against `weather_cache` forecast for the relevant
     date; adverse items flagged (`weather_flag`) with a suggested indoor/alternative swap
     (`weather_alternative_suggestion`)** — the fifth check `ARCHITECTURE_REVIEW.md` H7 found
     missing, implemented Phase 6 via a real OpenWeatherMap client
     (`app/services/weather_client.py`) cached in `weather_cache`; degrades to "do not flag"
     (never guesses) when no `WEATHER_API_KEY` is configured
5. Persist trips/itinerary_days/itinerary_items; set trips.generation_status
6. Return to client
```

**Failure handling (FR-001 exception flow):** if step 3 times out or the gateway raises after retry-with-backoff, the pipeline serves a **pre-authored curated fallback template** for the destination (a static, hand-built itinerary stored as seed data, not AI-generated) and sets `generation_status = 'fallback_used'`. This is a hard requirement, not an optimization — it is the difference between "the AI is down" and "the product is down."

**Clarification flow (FR-001 alt. flow):** if required inputs (budget, dates, destination) are missing, the pipeline does **not** call the LLM at all — it returns a `CLARIFICATION_NEEDED` response (max 2–3 targeted questions, never a blank "please provide more info").

---

## 3. Idea Extraction (FR-005, pre-processing step)

Runs on `POST /trips/{trip_id}/notes` before itinerary generation:

```
1. LLMGateway.complete() with a structured-extraction schema:
   { "places": [...], "dates_mentioned": [...], "activities": [...], "confidence": "..." }
2. Extracted places are validated against the pois table (fuzzy match by name + destination);
   unmatched names are still passed forward as free-text hints to step 1 of the Itinerary Generation
   Pipeline, never silently dropped (FR-005 business rule).
3. unparsed_remainder = original text minus confidently-extracted spans; stored verbatim and
   always shown back to the user alongside the generated plan (FR-005 acceptance criteria).
4. Conflict detection: if extracted places imply an unrealistic same-day combination
   (e.g. two cities >4h apart), flag it — the pipeline does not silently resolve this itself,
   it surfaces the conflict to the user (FR-005 exception flow) via the itinerary-generation response.
```

---

## 4. Conversational Modification Pipeline (FR-004)

**Trigger:** `POST /trips/{trip_id}/itinerary/modify`

```
1. Load current itinerary_items + ai_conversations history for this trip (multi-turn context, §19.2
   "Personalisation/context management") + the traveller's own onboarding interests / travel style /
   pace. Prior turns are replayed as real conversation messages (user/assistant roles), not
   flattened into the context blob, so the model can see that IT asked the clarifying question the
   traveller is now answering; the window is capped (§12 cost controls) and never opens on an
   assistant turn. The profile block is omitted entirely for a traveller who has no preferences yet.
   Both were added in the Gemini certification pass — see PHASE_STATUS.md "Gemini integration
   certification" for the live evidence that motivated each.
2. LLMGateway.complete() interprets the request against current state; output is a *scoped diff*
   (which itinerary_items change), never a full itinerary regeneration — this is what guarantees
   "only the relevant segment changes, rest of plan preserved" (FR-004 acceptance criteria)
3. Proposed diff re-enters the same business-rule validator used in Itinerary Generation step 4
4. If the diff violates a hard rule (e.g. new time pushes an item outside opening hours):
   respond with the conflict explanation + the closest valid alternative (FR-004 exception flow) —
   the validator, not the LLM, is the source of truth for "is this allowed"
5. If the request is ambiguous (e.g. "make it better"): return a single clarifying question
   instead of guessing (FR-004 alt. flow)
6. On user acceptance, apply the diff and log an explicit_correction feedback_signal if the change
   contradicts a prior AI suggestion (feeds the Personalization Engine, §16 business rule:
   explicit correction always overrides inferred preference, immediately and for future recommendations)
```

---

## 5. Heritage Narration RAG Pipeline (FR-007) — the product's most distinctive AI system

This is treated with the most care of any AI system in the product, per §22: the founder's own motivating example (a costly human guide at the Taj Mahal) is a heritage-narration problem specifically, and a confidently wrong historical claim "does more damage than an honestly missing one" (§43.1).

### 5.1 Content ingestion (offline, admin-triggered — not a runtime request path)

```
1. Admin authors/curates heritage_content rows (layer=overview|deep, section_title, body_text,
   source_citation) sourced from vetted references only — official tourism/heritage body materials,
   licensed content. Never scraped from arbitrary web sources (§22, §27 "AI data protection").
2. On PATCH /admin/heritage-content/{id}/publish:
   a. Content is chunked (target ~300–500 tokens per chunk, sentence-boundary aware, so a chunk
      never straddles a section it can't stand alone as a citation for)
   b. Each chunk embedded via LLMGateway.embed() → heritage_content_embeddings row
   c. is_published flips to true only after embeddings succeed (atomic — no half-published content
      that has published text but no retrievable embedding, or vice versa)
3. Content is versioned (heritage_content.version); re-publishing a correction re-embeds and the old
   embedding rows for that content_id are superseded (soft-retired, not deleted, for audit trail).
```

### 5.2 Runtime retrieval + generation

**Trigger:** `GET /heritage/{poi_id}/narration`

```
1. Embed the request context (poi_id + requested layer/section) — or, for a static "give me the
   overview" request, retrieval can be a straight poi_id + layer filter with no embedding call needed;
   embedding-based retrieval is reserved for section-level semantic navigation ("tell me about the
   carvings near the entrance") where a plain filter isn't precise enough.
2. Vector search: cosine similarity over heritage_content_embeddings WHERE heritage_content.poi_id = ?
   AND is_published, top-k (k=4–6) chunks retrieved
3. LLM composition: LLMGateway.complete() is given ONLY the retrieved chunks as source material,
   with an explicit system-prompt instruction: "Answer only using the provided source material.
   If the source material does not cover the question, say so — do not use outside knowledge."
   This is the RAG grounding contract (§19.2) that prevents "unguided model memory" from generating
   historical claims.
4. Confidence flag: derived deterministically from retrieval quality — if the top retrieved chunk's
   similarity score is below a tuned threshold, OR the model's output includes its own
   self-reported low-confidence marker, the response is flagged confidence="low" and the client
   renders a "verify locally" disclaimer (§28 edge case, FR-008/FR-007 business rule). This flag is
   NEVER computed by asking the same LLM call "are you confident?" as an afterthought — it is a
   structural property of the retrieval step, which is far harder for the model to get wrong.
5. If no published content exists for the poi_id at all: 404 POI_NOT_COVERED, no LLM call made,
   no fabricated narration under any circumstance (FR-007 exception flow — a hard rule, not a
   preference).
```

### 5.3 Golden-set evaluation (ties to `TESTING_PLAN.md` §AI Response Evaluation)

For every launch POI (the curated 5–10 flagship set, §29.1), a versioned "golden set" of known-correct question→answer pairs is maintained and re-run on **every change** to prompts, retrieval parameters, or the underlying content — this is the primary regression guard against silent narration-quality drift (§34).

---

## 6. Visual Q&A Pipeline (FR-008)

**Trigger:** `POST /heritage/{poi_id}/photo-qa`

```
1. Image validation: format/size/quality check. Unusable image → 422 IMAGE_UNUSABLE,
   "please retake" (FR-008 exception flow) — no analysis attempted on an unusable input.
2. LLMGateway.complete_multimodal() — the photo + question + the same retrieved heritage_content
   chunks for this poi_id (step 5.2.2 above) are passed together, so the model answers about the
   *specific detail in the photo* grounded in the *same verified source material* as the narration
   feature, not a separate unguided vision call.
3. Confidence flagging: same structural approach as §5.2.4 — if the retrieved content doesn't
   plausibly cover what's in the photo (low retrieval-relevance score, or the model itself cannot
   tie the visual content to any retrieved chunk), confidence="low" is returned and visibly flagged,
   never presented with the same certainty as a grounded answer (FR-008 business rule).
4. If no confident POI/content match exists at all: the system still answers as generally as it can
   from the photo alone (general vision capability, no RAG grounding) and invites the user to
   rephrase/specify (FR-008 alt. flow) — this is the one path where an ungrounded answer is
   acceptable, and it is always labeled as such.
5. Response logged to ai_messages (role='assistant', confidence=...) for audit and future
   golden-set expansion.
```

---

## 7. Personalization / Recommendation Engine (§20)

Hybrid system, exactly as specified in §19.2 — never a single technique alone:

| Component | Role |
|---|---|
| **Rule-based filters** | Hard constraints: budget, opening hours, geographic reachability. These can reject a candidate outright; they are never "soft" |
| **Embedding similarity** | Matches free-text interests / accumulated taste profile (`personalization_profile.taste_embedding`) against POI/heritage-content embedding space — this is how "likes heritage + food, dislikes crowds" becomes a ranked candidate list, not just a keyword filter |
| **Behavioral/review signal** | `feedback_signals`, `reviews.rating`, favorites/collections activity boost or suppress candidates |

### 7.1 Cold-start handling (§20)

```
New user (no feedback_signals yet):
  weight = 100% explicit onboarding (profile_interests) + curated/popular-POI defaults
As trips complete and feedback accumulates:
  weight shifts progressively toward learned behavioral signal
  (implemented as a decayed weighted average recomputed by a scheduled job — see
  DEPLOYMENT_PLAN.md §Scheduled Jobs — writing to personalization_profile.preference_weights;
  not recomputed synchronously on every request, to keep itinerary-generation latency inside
  the §15 8–12s target)
```

### 7.2 The one hard business rule this engine must never violate

> An explicit user correction always overrides an AI-inferred preference — immediately, and for future recommendations, not just the current session (§16, §20).

Implementation: an `explicit_correction` `feedback_signals` row is applied as an **immediate, synchronous write** to `personalization_profile.preference_weights` (not queued for the next scheduled batch job) specifically because this rule is called out twice in the PRD as non-negotiable (§16 Business Rules, §20 Personalisation Engine). All other signal types (implicit accept/reject, review sentiment) go through the batched recompute in §7.1.

---

## 8. Dynamic Re-Adaptation Engine (FR-014, Phase 2)

Monitors the reactive triggers listed in §21.1 (weather change, POI closure/hours change, delay, off-route, missed activity, budget overrun, schedule change, direct user request) and, on detection:

```
1. Re-evaluate only the remaining (not-yet-completed) itinerary items against current conditions
2. Generate top 2–3 alternatives (not one forced choice, §21.1 alt. flow) via the same
   Itinerary Generation candidate-retrieval step (§2.2), constrained to the affected time slot
3. Attach a short plain-language reason to each proposal (§21.2 design principle)
4. Write a disruption_events row with status='proposed' — nothing is applied to itinerary_items
   until the user explicitly accepts (§16, §21.2: "every adjustment is presented... before it
   takes effect")
5. If no reasonable alternative exists (e.g. everything nearby is also closed): return that
   plainly rather than forcing a poor suggestion (FR-014 exception flow)
```

Notification volume is deliberately throttled (§21.2: "the goal is an itinerary that adapts intelligently, not an app that interrupts constantly") — disruption checks run on a scheduled cadence (not on every single location ping) and de-duplicate against any still-`proposed` event for the same itinerary item.

---

## 9. Group Preference Reconciliation (FR-012, Phase 2 → richer in Phase 4)

**Phase 2 (rule-based-first):**
```
1. Collect trip_preferences from all responded members
2. Merge interests (union, weighted by member count), take the intersection of hard constraints
   (e.g. must-include places named by any member are candidates; budget = min of members' budget_max
   unless a tiered-alternative flag is used)
3. Where members' stated interests/budgets genuinely conflict, generate the itinerary from the
   reconciled set AND separately list each conflict + how it was resolved (FR-012 business rule:
   "proposes a reconciled option and explains the trade-off rather than silently choosing one
   member's preference")
4. Non-responding members: organiser can proceed; the response marks which members' input was
   actually included (FR-012 exception flow)
```
**Phase 4 upgrade (F32):** the same reconciliation step is upgraded from rule-based merging to an LLM-assisted negotiation pass that can propose creative compromises (e.g. splitting a day so different sub-groups do different activities) — same guardrail (always show the trade-off, never silently pick) carries forward unchanged.

---

## 10. Guardrails & Prompt Engineering (§19.2)

| Guardrail | Enforcement point |
|---|---|
| Narration/Q&A never states unverified claims as fact | RAG grounding contract (§5.2.3) + confidence flagging (§5.2.4) — structural, not just prompt wording |
| Assistant stays on-topic (travel companion, not general chatbot) | System prompt scope restriction + a lightweight topic classifier on `POST /trips/{id}/itinerary/modify` and the general chat endpoint; off-topic requests get a polite redirect, not a refusal wall |
| No unsafe/irrelevant outputs | Provider-level content-safety settings enabled on every LLMGateway adapter; a second, product-specific check rejects any generated itinerary item referencing a POI not present in the candidate set from retrieval (prevents hallucinated venues, §2.3) |
| Consistent companion tone | Shared system-prompt template library (`services/ai/prompts/`), versioned alongside code, reviewed the same way as any other change (§33 code review) |
| Adversarial/prompt-injection resistance | User-provided free text (trip notes, chat, photo questions) is always passed as clearly-delimited *data*, never concatenated into the system/instruction prompt — standard prompt-injection mitigation, tested via the adversarial-prompt test suite in `TESTING_PLAN.md` |

---

## 11. AI Evaluation Strategy (§34, the "least off-the-shelf" test dimension)

| Evaluation type | What it catches | Cadence |
|---|---|---|
| Golden-set narration regression (§5.3) | Factual drift in heritage content after a prompt/retrieval/content change | Every PR touching `services/ai/*` or `heritage_content` |
| Itinerary golden set | Budget/time/interest-fit correctness | Every PR touching the generation pipeline |
| Human review sampling | Catches issues golden sets don't (novel hallucinations, tone drift) | Weekly sample of production `ai_messages`, tagged `confidence` distribution reviewed |
| Adversarial prompt tests | Guardrail bypass attempts, injection via trip notes/photo questions | CI, before every release |
| Hallucination-flag rate (production metric) | Trend over time — a KPI, not just a test (§37) | Continuous, dashboarded (`DEPLOYMENT_PLAN.md` §Monitoring) |

Full test-tooling detail (framework choices, CI gating) lives in `TESTING_PLAN.md` §AI Response Evaluation.

---

## 12. Cost Controls (§38 risk: "LLM/API cost overrun at scale")

- Rate limiting at the API layer (`API_SPECIFICATION.md` §1) is the first line of defense. **Phase 6 implementation:** `app/core/rate_limit.py`, an in-process per-user token bucket (10 req/min on every AI endpoint — itinerary generate/modify, translate text/speech, photo-qa). This is the PRD §26.4 Caching row's own documented Alternative for `ARCHITECTURE_REVIEW.md` H3 ("in-memory cache within the API layer for the earliest MVP"), adopted explicitly with the stated single-instance constraint recorded — it is NOT correct once this backend runs as more than one instance, and must be replaced with a Redis-backed store before that happens.
- `heritage_content_embeddings` retrieval is cached per `(poi_id, layer, section)` for a short TTL — repeated requests for the same static narration don't re-run retrieval+generation.
- Weather/Maps responses cached (`weather_cache` table, §DATABASE_SCHEMA.md) rather than re-fetched per request.
- Prompt/response size budgets enforced per endpoint (max input tokens truncates oldest chat history first, not silently drops the current request).
- Model tier is configurable per pipeline (e.g. a cheaper/faster model for Idea Extraction's structured parsing vs. a stronger model for narration composition) — the LLMGateway abstraction (§1) makes this a per-call config choice.
- Cost-per-request logged to `analytics_events` (`ai_messages.tokens_used`) and dashboarded — see `DEPLOYMENT_PLAN.md` §Monitoring.

---

## 13. What the AI Layer Is Explicitly Not (scope discipline, §43)

- Not a general-purpose chatbot — every conversational surface is scoped to travel planning/companionship (§10).
- Not a source of unverified historical fact — RAG grounding is mandatory for narration and Q&A; the model's own "memory" is never the source for a factual claim about a heritage site (§19.2, §22).
- Not a self-hosted/trained model — orchestration only, over hosted provider APIs (§26.4, §39).
- Not a dating/matching engine, even though the same recommendation engine powers Quick Plans for dates/hangouts (§43.2) — no matching, discovery-of-strangers, or messaging-between-users functionality exists anywhere in this architecture.
