# Mobile Architecture
## React Native + Expo Client — AI Personalized Tourist Guide (TC-SO1)

Companion to `IMPLEMENTATION_BLUEPRINT.md`. Implements PRD §25 (UX/UI Requirements) — conversational-first, two visually distinct modes (Planning vs. On-Trip) — on top of the frontend layer named in the target architecture.

---

## 1. Stack

| Concern | Choice | Rationale |
|---|---|---|
| Framework | React Native + Expo (managed workflow, EAS Build) | PRD-recommended (§26.4) + lean-team DevOps minimization (§40) |
| Language | TypeScript | Type-safe contracts against the FastAPI OpenAPI schema (generated client, §9 below) |
| Navigation | React Navigation (native-stack + bottom-tabs) | Standard, well-supported in Expo managed workflow |
| State/data | TanStack Query (server state) + Zustand (local/UI state) | Server state (trips, itinerary, notifications) is cache-and-sync by nature — TanStack Query's staleness/refetch model fits directly; Zustand covers ephemeral UI state (active mode, composer drafts) without Redux boilerplate |
| Auth client | `@supabase/supabase-js` with an Expo `SecureStore`-backed storage adapter | Matches the Supabase Auth decision in `IMPLEMENTATION_BLUEPRINT.md` §1.3; tokens never touch plain `AsyncStorage` |
| Maps | `react-native-maps` (Google provider on both platforms) | Matches Google Maps Platform integration (Module 9) |
| Location | `expo-location` + `expo-task-manager` (background task) | Needed for FR-006 arrival detection while the app is backgrounded |
| Camera/Media | `expo-image-picker` | FR-008 Visual Q&A (Phase 6). **Documented decision:** `launchCameraAsync`/`launchImageLibraryAsync` cover both camera capture and gallery pick without the separate live-camera-preview component `expo-camera` provides — that component isn't needed for a single-shot "attach a photo" flow. A shared `useCameraCapture()` hook was not extracted (§6 below originally proposed one) since `MemoryBoxScreen` (its second intended caller, F11) doesn't exist yet — one real call site (`PhotoQAScreen`) doesn't justify the abstraction yet; extract it when F11 is built. |
| Voice/Speech | `expo-audio` | F25 speech translation (Phase 6) — `useAudioRecorder`/`useAudioRecorderState` for batch clip recording; see §13 below for the real-time-vs-batch boundary. |
| Push | `expo-notifications` | Delivers via FCM/APNs under the hood — see `IMPLEMENTATION_BLUEPRINT.md` §1.2 |
| Local storage/offline | `expo-sqlite` (structured offline cache: itinerary, heritage content, phrasebook) + `expo-file-system` (downloaded media/map tiles) | Backs F26 Offline Heritage Access (Phase 2) |
| Forms/validation | `react-hook-form` + `zod` (schemas shared conceptually with backend Pydantic models) | Keeps client-side validation in sync with API contract shapes |
| Testing | Jest + React Native Testing Library (unit/component), Maestro (E2E) | See `TESTING_PLAN.md` §Mobile |

---

## 2. Navigation Structure

```
RootNavigator
├── AuthStack                         (unauthenticated)
│   └── SignInScreen
├── OnboardingStack                   (first login only, ≤6 screens, §15 usability target)
│   ├── InterestSelectScreen
│   ├── TravelStyleScreen
│   ├── BudgetBracketScreen
│   └── OnboardingCompleteScreen
└── MainTabNavigator                  (authenticated + onboarded)
    ├── HomeTab
    │   └── HomeScreen                (upcoming trip, quick actions, Quick Plan entry — §25.1)
    ├── TripsTab
    │   ├── TripsListScreen           (grouped upcoming/active/completed, US-020)
    │   └── TripDetailStack           (pushed from TripsListScreen)
    │       ├── TripCreationScreen    (destination/dates/budget/interests + "my own ideas" input)
    │       ├── ChatScreen            (conversational planner — primary interaction surface, §25)
    │       ├── ItineraryViewScreen   (map + timeline hybrid, §25.2)
    │       ├── OnTripCompanionScreen (mode-switched automatically when trip.status = 'active', §25.2)
    │       ├── HeritageNarrationScreen
    │       ├── PhotoQAScreen
    │       ├── PhrasebookScreen
    │       ├── BudgetViewScreen
    │       ├── MemoryBoxScreen
    │       ├── SafetyScreen          (Phase 2)
    │       └── GroupInviteScreen     (Phase 2)
    ├── CollectionsTab
    │   ├── CollectionsScreen
    │   └── FavoritesScreen
    └── ProfileTab
        ├── ProfileScreen
        ├── PreferencesScreen
        └── NotificationsCentreScreen
```

Modals (presented over any stack, not tab-scoped): `SOSModal` (Phase 2, persistent quick-access), `ShareTripModal` (Phase 2), `PhotoCaptureModal`.

**Phase 8 implementation note:** `SafetyScreen` and `GroupInviteScreen` are now real, built screens (F21/F19) — reachable, per this project's already-established flat-`RootNavigator`-stack precedent (not the `MainTabNavigator` sketched above — see this document's own Phase 5 decision, still unreversed), via a "Safety"/"Group" tool button on `ItineraryViewScreen`'s tool row, not a persistent tab. `QuickPlanScreen` (F22) is reachable from a "Quick plan" entry card on `HomeScreen`, matching the "Quick Plan entry" wording in the sketch above. No `SOSModal`/`ShareTripModal` were built as modals specifically — `SafetyScreen` hosts the SOS button and share start/stop inline instead, a real, working simplification (one screen, not a screen plus two modals) rather than a gap.

---

## 3. Dual-Mode UX Implementation (§25.2 — the PRD's core experience principle)

The PRD requires two visually distinct interaction modes rather than one interface serving both. This is implemented as a **derived UI mode**, not a separate app:

```
tripUIMode = trip.status === 'active' ? 'on_trip' : 'planning'
```

- **Planning mode** (`draft`/`upcoming` trips): `ItineraryViewScreen` is the default landing screen inside a trip — dense information, comparison, editing affordances, full chat composer visible.
- **On-Trip mode** (`active` trips): `OnTripCompanionScreen` becomes the default landing screen — glanceable cards, minimal typing, large tap targets (§25.2: "used while moving"). The chat composer collapses to a single quick-input bar; narration and phrasebook are one tap away via persistent shortcut chips rather than nested menus.
- Every AI-adjusted plan change (from `POST .../itinerary/modify` or an accepted disruption proposal) renders with its one-line reason inline, in both modes — never applied silently (§16, §21.2, §25.2).
- Consent prompts (location, camera, notifications) are custom pre-permission screens shown **before** the native OS prompt, explaining the specific benefit unlocked (§25.2) — e.g. "Turn on location to get notified the moment you arrive at each stop" before the OS location dialog fires. This avoids the generic-permission-request pattern the PRD explicitly calls out.

---

## 4. State Management Detail

| Layer | Tool | Scope |
|---|---|---|
| Server state | TanStack Query | Trips, itinerary, POIs, heritage content, notifications, reviews, memory items — anything owned by the backend. Query keys namespaced by trip/resource id; mutations use optimistic updates only where the PRD's "never silently apply a change" rule doesn't apply (e.g. optimistic favorite-toggle is fine; optimistic itinerary-diff application is NOT — that must wait for the server's validated response, per §16) |
| Session/auth state | Supabase client + a thin `useAuth()` context wrapper | Current user, session token, onboarding-completion flag |
| Local UI state | Zustand | Active tab, composer draft text, camera-modal open/closed, current `tripUIMode` override (rare manual toggle) |
| Offline cache | `expo-sqlite`, hydrated from TanStack Query's persisted cache (`@tanstack/query-async-storage-persister` backed by SQLite) | Itinerary, heritage narration, phrasebook entries downloaded per F26 |

---

## 5. Location & Background Tracking (FR-006)

```
1. Foreground: expo-location watchPositionAsync, throttled (distance/time interval tuned to
   balance §15 latency target against battery — Proposed Target: update on 50m movement or 60s,
   whichever first, only while a trip is 'active' and the screen is OnTripCompanionScreen or
   backgrounded during an active trip)
2. Background: expo-task-manager background task registered only after explicit per-trip
   opt-in consent (BR-014) — the custom pre-permission screen (§3 above) gates the OS permission
   request, and a second, product-level "share my location for this trip" toggle gates whether
   pings are actually sent to the backend even if OS permission is granted (two-layer consent:
   OS-level capability + product-level intent, matching §27's "opt-in per trip, pausable/stoppable
   at any time")
3. Each ping → POST /trips/{trip_id}/location/ping (API_SPECIFICATION.md §6); arrival events and
   nearby recommendations returned in the same response drive local push notifications and
   OnTripCompanionScreen updates
4. Permission denied/revoked mid-trip → location-dependent UI (arrival cards, nearby suggestions)
   swaps to a manual "I'm at ___" input; rest of the app (chat, itinerary, memory box) unaffected
   (FR-006 exception flow) — enforced via a single isLocationAvailable flag read by every
   location-dependent component, not scattered permission checks
```

**Phase 7 implementation note (read before assuming step 2 above is built):** `OnTripCompanionScreen`
implements step 1 (foreground `watchPositionAsync`, active only while the screen is mounted, plus an
explicit "Check in now" manual trigger) and steps 3/4 in full, against the real F7 backend
(`POST /trips/{id}/location/{consent,ping,manual}`, `GET /trips/{id}/nearby`). Step 2 — a true
`expo-task-manager` background task (`TaskManager.defineTask` + `Location.startLocationUpdatesAsync`
with `ACCESS_BACKGROUND_LOCATION`/iOS "Always" permission) and the custom pre-permission explainer
screen referenced in §3 — is **NOT implemented this phase**. `expo-location` itself is installed and
configured (`app.config.js`'s `expo-location` plugin), but the always-on background variant requires
native permission flows and battery/OS-kill behavior this environment has no physical device or
simulator to verify, and was judged unsafe to ship unverified. Documented here as a deliberate,
real scope boundary (CLAUDE.md §13), not a silent gap — tracked in `docs/PHASE_STATUS.md`'s Phase 7
section as a specific Known Limitation.

---

## 6. Camera / Photo Q&A (FR-008) & Memory Box Uploads (FR-010)

- Shared `useCameraCapture()` hook wraps `expo-image-picker`/`expo-camera`, used by both `PhotoQAScreen` and `MemoryBoxScreen` upload flow — same capture UX, different destination.
- Photo Q&A: capture → local preview → question composer (text or voice-to-text via device dictation, no custom speech pipeline needed for MVP) → `POST /heritage/{poi_id}/photo-qa`. Poor-quality capture is caught client-side first (basic blur/size heuristic) before the network call, to avoid a round trip for an obviously unusable image; the server-side check (`AI_ARCHITECTURE.md` §6) remains the authoritative gate.
- Memory Box (Phase 7, `MemoryBoxScreen`): capture/select via `expo-image-picker` → the mobile client's own authenticated Supabase session uploads the file **directly** to the `memory-items` Storage bucket (RLS-mediated, migration `20260825120013`) → `POST /trips/{id}/memory-items` records the resulting metadata only after the upload itself succeeds. No backend-issued signed URL is involved — the client's own session already satisfies the bucket's RLS policy, so a signed-URL round trip through the backend would be redundant (documented decision, `app/services/memory_service.py`'s own module docstring). Upload/delete failures are surfaced explicitly via an inline error state, never silently dropped (FR-010 exception flow).

---

## 7. Push Notifications (Module 20)

```
1. On login (post-onboarding), register for push: expo-notifications getExpoPushTokenAsync()
   → POST /devices/push-token
2. Notification categories map 1:1 to notifications.type: arrival, disruption, memory_expiry,
   sos, group_invite, reminder, system
3. Foreground notifications render as an in-app banner (not a native OS banner while the app is
   open) to avoid interrupting the current screen unnecessarily — tapping opens the relevant
   screen (deep link via notification payload). **Phase 7 note:** as built,
   `src/notifications/pushNotifications.ts` uses Expo's own native foreground banner
   (`setNotificationHandler({ shouldShowBanner: true, ... })`) rather than a custom in-app banner
   component — a real, working simplification, not a gap; a custom banner UI can be layered on
   later without changing the registration/delivery path documented here.
4. NotificationsCentreScreen is the guaranteed fallback channel (§24) — every notification is
   also written to the notifications table and visible there even if push delivery failed
5. Notification volume is intentionally kept low per §21.2 — the client does not add its own
   client-side notification triggers beyond what the backend sends; no "engagement" notifications
   invented outside the PRD's specified triggers (arrival, disruption, expiry reminder, SOS,
   group invite)
```

---

## 8. Maps Integration (Module 9)

- `react-native-maps` with the Google provider renders `ItineraryViewScreen` (all stops + route polyline) and `OnTripCompanionScreen` (current position + next stop + nearby pins).
- The client **never calls Google Maps/Places APIs directly with an embedded key** for data operations — POI search/detail/nearby goes through the FastAPI proxy (`API_SPECIFICATION.md` §5) so the API key stays server-side and usage/cost can be centrally rate-limited (§27). The map *rendering* SDK itself (tile display) does require a client-side Maps SDK key (standard Google Maps Platform requirement for the RN SDK), which is a different, tile-rendering-scoped key from the Places/Directions key used server-side, and is restricted (Android package name / iOS bundle ID) in the Google Cloud Console.
- Map-tile load failure → automatic fallback to a list view of the same stops (§24), implemented as an error boundary around the map component that swaps in `ItineraryListFallback`.

---

## 9. API Client Layer

- FastAPI exposes an OpenAPI schema; a typed TypeScript client is generated from it (`openapi-typescript` + a thin fetch wrapper) so request/response shapes are compiler-checked against `API_SPECIFICATION.md`, not hand-maintained.
- A single `apiClient` instance injects the current Supabase JWT into every request and handles 401 → silent token refresh → retry-once, matching FR-002's "returning user signed in silently."
- Idempotency keys (UUID v4, generated client-side) attached automatically to all POST mutations, per `API_SPECIFICATION.md` §1.

---

## 10. Design System (§25, Phase 4 of the SDLC in the PRD — "UX/UI Design")

- A minimal token-based design system (`theme/`: color, spacing, typography, radius tokens) shared across both UX modes, with mode-specific density variants (Planning = comfortable spacing/smaller tap targets acceptable; On-Trip = large tap targets, higher-contrast glanceable cards) rather than two separate visual languages.
- Component library built once (`components/`: `Card`, `Button`, `ChatBubble`, `POIListItem`, `MapPin`, `ConfidenceBadge` — the last one specifically renders the AI confidence flag from `AI_ARCHITECTURE.md` §5.2.4/§6 consistently everywhere a grounded answer appears) and reused across screens — no per-screen bespoke styling.
- Accessibility: WCAG 2.1 AA aspiration (§15, TBC) — enforced via `react-native` accessibility props (`accessibilityLabel`, `accessibilityRole`) reviewed at component-library level so every screen inherits compliant primitives by default.

### 10a. UI/UX Overhaul + Language Settings phase (documented decisions, CLAUDE.md §13)

- **Visual language**: the Phase-1 neutral/light token set was replaced with a dark indigo-violet palette (`gradients`, `shadow` tokens added to `theme/tokens.ts`) matching a supplied design reference. `app.config.js`'s `userInterfaceStyle` moved from `light` to `dark` and every screen's `StatusBar` moved from `style="dark"` to `style="light"` accordingly. The Planning-mode/On-Trip-mode density distinction in §3 is unchanged — this is a re-skin of the same shared token system, not a new visual language per mode.
- **New shared components**: `GradientBackground`, `ScreenHeader` (replaces each screen's own ad hoc back-button/title markup), `EmptyState`/`ErrorState` (standardize the loading/empty/error/retry states §14/CLAUDE.md §11 already required per-screen), `IconBadge`, `BottomNavBar`.
- **Bottom navigation**: implemented as a persistent `BottomNavBar` component (Home/Trips/Explore/Profile + an elevated center action) calling the existing single stack's `navigation.navigate()` — deliberately NOT a nested `Tab.Navigator` restructuring of §2's `RootNavigator`. Native-stack's `navigate()` (unlike `push()`) already returns to an existing route instance already in the stack instead of piling up duplicates, giving genuine tab-like switching without touching the navigation param dependencies of the ~20 screens already wired to `RootStackParamList`. The center action opens `TripCreation` (real AI trip planning) rather than `Chat`, which requires a `tripId` a nav bar has no way to supply.
- **New screens**: `ProfileScreen`, `SettingsScreen`, `LanguageSettingsScreen` — the account/settings surface implied by §2's tab structure did not exist before this phase; added as plain stack screens, reachable from the new `BottomNavBar`'s Profile tab.
- **i18n**: `src/i18n/` — `LanguageContext` (local-first persistence via the existing `expo-secure-store` adapter + best-effort sync to `profiles.preferred_language`), static per-language resource files (`locales/{en,hi,te,ml,kn,ta}.ts`), dot-path `t()` lookup with English fallback for any missing key. First-run device-locale detection via `expo-localization`. Full detail and the "hero vs. standard namespace" translation-depth decision are in `docs/PHASE_STATUS.md`'s UI/UX Overhaul + Language Settings phase entry.

### 10b. Minimal monochrome theme + light/dark appearance (documented decisions, CLAUDE.md §13)

- **Visual language**: the §10a violet/indigo gradient palette was replaced with a strictly greyscale system — whites, blacks and greys only, no hue anywhere in the app. Light mode is a white page with a black accent; dark mode is a black page with a white accent. Surfaces are flat and separated by 1px borders rather than gradients, glows or heavy shadows (light mode keeps a barely-visible card shadow so white cards still separate on hardware; dark mode uses none). Even the semantic tokens (`success` / `warning` / `error` / `gold`) are greys: status meaning is carried by icon and label, the token only sets emphasis. Corner radii were tightened (`radius.md` buttons, `radius.lg` cards; `pill` reserved for chips, badges and circular icon buttons).
- **Theme runtime** (`src/theme/`): `tokens.ts` now exports `lightColors` / `darkColors` (`ThemeColors`), the static `spacing` / `radius` / `typography`, and two prebuilt `Theme` objects. `ThemeContext.tsx` provides `ThemeProvider` (owns the user's Appearance preference — `system` / `light` / `dark` — persisted locally through the same `expo-secure-store` adapter the language setting uses, key `yatra_theme_mode`), `useTheme()` (resolved colors + `isDark` + the preference controls; degrades to following the OS scheme with a no-op setter when no provider is mounted, so isolated component tests and the root error fallback never throw), `useThemedStyles(factory)` (the per-file replacement for a static `StyleSheet.create`: a module-level `(theme) => StyleSheet.create({...})` factory memoized per scheme) and `ThemedStatusBar` (the single status-bar owner, rendered once in `App.tsx`). Everything imports from the `src/theme` barrel; the old static `colors` / `gradients` / `shadow` exports were removed on purpose so the type checker flags any call site that would otherwise silently stay on one scheme.
- **Navigation**: `RootNavigator` passes a theme derived from the app theme to `NavigationContainer` so transitions and the container behind them use the page color (no white flash in dark mode, no dark flash in light mode). `app.config.js`'s `userInterfaceStyle` moved from `dark` to `automatic`.
- **Backdrop**: `GradientBackground` was deleted and replaced by `components/Screen` (a flat page in the theme background). `expo-linear-gradient` is no longer used and was removed from the dependency list.
- **Settings**: `SettingsScreen` gained an Appearance section (System / Light / Dark segmented control) wired to `ThemeProvider`; strings live in every locale under `settings.appearance*`.
- **Planning vs. On-Trip density** (§3) is unchanged — this is a re-skin of the same shared token system, not a new visual language per mode.

---

## 11. Offline Behavior Summary (ties to F26, Phase 2)

| Data | Offline behavior |
|---|---|
| Downloaded trip itinerary | Read-only cache via SQLite-persisted TanStack Query cache |
| Downloaded heritage narration | Full read access via `expo-sqlite`, pre-fetched on `POST /trips/{id}/phrasebook/download`-equivalent heritage package endpoint |
| Downloaded phrasebook | Full read access, same mechanism |
| Map tiles | Cached tile package for the trip's region (Phase 3, F28) |
| Anything not pre-downloaded | Standard "you're offline" state, no crash — cached itinerary/heritage/phrasebook remain usable read-only per §28 edge case ("Internet unavailable → serve cached itinerary and any pre-downloaded heritage/phrase content, read-only") |

MVP (Phase 1) ships without the offline package feature itself (that's Phase 2 per §29.2) — but the client's data layer (TanStack Query + SQLite persister) is built from day one so offline support is additive, not a retrofit.

**Phase 8 implementation note:** as built, `ItineraryViewScreen`'s "Download for offline" action calls the real `GET /trips/{id}/offline-package` (F26) and persists the response as one JSON file via `expo-file-system`'s `File`/`Directory` API (`Paths.document/offline-packages/{tripId}.json`) — a real, working, verified round trip (download → write → the file genuinely exists on disk), not the `expo-sqlite`-backed structured cache this document originally sketched. `expo-sqlite` remains unused by this feature; adopting it (and reading cached content back into the itinerary/heritage/phrasebook screens automatically when a live request fails) is real follow-up work, not yet built. Map-tile caching (the fourth row above) remains genuinely out of scope — no verifiable first-party `react-native-maps` offline-tile API exists to build against (`app/services/offline_service.py`'s own documented decision).

---

## 12. Build & Release (client half — full detail in `DEPLOYMENT_PLAN.md`)

- EAS Build produces store-ready iOS/Android binaries; EAS Submit automates store upload; EAS Update ships JS-only patches over-the-air between store releases (for non-native-code fixes), consistent with the PRD's staged dev→staging→production promotion (§35) — OTA channels map to the same three environments.

---

## 13. F25 Speech Translation — Capability Boundary (Phase 6)

`TranslateScreen`'s "🎤 Speak instead" control is **batch** audio capture, not a continuous live voice conversation: `useAudioRecorder` records a clip, the traveller taps stop, the whole clip uploads to `POST /translate/speech`, and a single transcription+translation comes back once processing completes (a few seconds' round trip, not a live captioned stream). This is stated explicitly because "live translation" language appears elsewhere in this product's naming (F25's own PRD title) — true continuous bidirectional voice-to-voice would require Gemini's separate Live API (WebSocket audio streaming) wired through a persistent connection on both client and server, which is materially more infrastructure than this phase's scope and is **not implemented**. The batch flow is real (genuine Gemini audio understanding, no canned response), just not real-time in the streaming sense.
