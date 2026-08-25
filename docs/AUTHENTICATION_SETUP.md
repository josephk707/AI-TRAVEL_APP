# Authentication Setup
## Google OAuth via Supabase Auth — AI Personalized Tourist Guide (TC-SO1)

Companion to `API_SPECIFICATION.md` §2 (endpoint contract), `DATABASE_SCHEMA.md` §3 (`profiles`, `handle_new_user()` trigger), and `MOBILE_ARCHITECTURE.md` §1/§4 (auth client, `useAuth()` context). This document is Phase 3's required setup/reference doc: how the real identity system is wired together, and how to configure, test, and troubleshoot it.

There is no custom authentication in this system. Supabase Auth (GoTrue) is the sole identity provider; Google OAuth is the sole sign-in method; the backend never stores a password or issues its own tokens.

---

## 1. Architecture

```
Mobile app (Expo)                Supabase Auth (GoTrue)         FastAPI backend         Postgres
------------------                ----------------------         ---------------         --------
supabase-js client
  .signInWithOAuth()  ─────────►  authorize URL (Google)
                                        │
                              (system browser, real Google
                               consent screen)
                                        │
  redirect back to app  ◄───────  aitouristguide://auth/callback?code=...
  (expo-web-browser
   openAuthSessionAsync)

  .exchangeCodeForSession(code) ──►  POST /auth/v1/token
                                     (PKCE code exchange)
  ◄── real session (access_token,
      refresh_token, user)

  stores session in
  expo-secure-store
  (Keychain/Keystore —
   never AsyncStorage)

  every API call attaches
  Authorization: Bearer
  <access_token>            ────────────────────────────────►  get_current_user()
                                                                  dependency:
                                                                  jwt.decode(token,
                                                                  SUPABASE_JWT_SECRET,
                                                                  verify sig/exp/aud/iss)
                                                                       │
                                                                       ▼
                                                                 ProfilesRepository
                                                                 (service-role pool,
                                                                  scoped by verified
                                                                  token subject) ───►  profiles
                                                                                       (RLS also
                                                                                        enabled —
                                                                                        defense in
                                                                                        depth, see §9)
```

Two independent layers enforce "a user can only ever see their own data":
1. **Application layer** — every `/v1/auth/*` handler derives the target row exclusively from `get_current_user()`'s verified token subject (`app/api/deps.py`, `app/repositories/profiles_repository.py`). No endpoint accepts a user id as a path/query/body parameter.
2. **Database layer (RLS)** — `profiles_select_own`/`profiles_update_own` policies (`DATABASE_SCHEMA.md` §3) independently enforce `auth.uid() = id`, verified directly against real ephemeral users in `backend/tests/test_rls_security.py`.

The backend's own Postgres connection (`DATABASE_URL`) runs with full table-owner privilege and therefore bypasses RLS — RLS is not what stops the *backend* from cross-user access (layer 1 does that); RLS is what stops anything else that might one day connect directly (a future PostgREST/Supabase client-side query, a misconfigured tool) from doing so, independent of the API layer being correct.

---

## 2. Auth flow, step by step

1. App cold-starts → `AuthContext` calls `supabase.auth.getSession()` to restore any persisted session from SecureStore. State: `AUTHENTICATING`.
2. No session found → state becomes `UNAUTHENTICATED` → `RootNavigator` renders `SignInScreen`.
3. User taps **Continue with Google** → `signInWithGoogle()`:
   a. `supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo, skipBrowserRedirect: true } })` — asks GoTrue for the Google authorize URL (PKCE flow: a code verifier is generated and its challenge embedded in this URL).
   b. `expo-web-browser`'s `openAuthSessionAsync(url, redirectTo)` opens the URL in a real, secure system browser session (`ASWebAuthenticationSession` on iOS, Chrome Custom Tabs on Android) — a real Google consent screen, not a WebView the app controls.
   c. User authenticates with Google and grants consent. Google redirects to Supabase's callback, which redirects again to the app's own redirect URI (`aitouristguide://auth/callback?code=...`) — `openAuthSessionAsync` captures this and returns it.
   d. `supabase.auth.exchangeCodeForSession(code)` exchanges the authorization code (with the PKCE verifier, held by the SDK) for a real session — this is the point a genuine, Supabase-signed JWT is issued. Never fabricated locally.
   e. The SDK fires `SIGNED_IN`; `AuthContext`'s listener sets state to `AUTHENTICATED`.
4. `RootNavigator` switches to `HomeScreen`, which calls `POST /v1/auth/session/bootstrap` (idempotent load — the `handle_new_user()` trigger already created the `profiles` row the instant step 3d's user was created in `auth.users`) then `GET /v1/auth/me`.
5. Every subsequent API call attaches `Authorization: Bearer <access_token>` (`src/api/client.ts`, reading the current session fresh via `supabase.auth.getSession()` — never a cached copy, so an SDK-driven token refresh is always picked up).
6. Sign-out: `POST /v1/auth/logout` (backend calls GoTrue's own `/auth/v1/logout` with the caller's token — revokes the refresh token server-side) → `supabase.auth.signOut({ scope: "local" })` clears the on-device session regardless of whether the network call succeeded.

---

## 3. Google Cloud OAuth client setup

Done once, in the Google Cloud Console, outside this repo:

1. Create (or reuse) a Google Cloud project → **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
2. Application type: **Web application** (yes, even though this is a mobile app — the OAuth flow is brokered through Supabase's own web callback, so Supabase's callback URL is what Google needs to trust, not a mobile deep link).
3. Authorized redirect URI: `https://<PROJECT_REF>.supabase.co/auth/v1/callback` (Supabase's own callback endpoint — find the exact value on the Supabase dashboard's Google provider settings page, §4 below, which shows it precomputed for your project).
4. Save the generated **Client ID** and **Client Secret** — these go into Supabase (§4), not into this app's own configuration. The mobile app and backend never see the Google client secret.

---

## 4. Supabase Auth provider setup

Done once, in the Supabase dashboard, outside this repo:

1. **Authentication → Providers → Google** → enable it, paste the Client ID and Client Secret from §3.
2. **Authentication → URL Configuration → Redirect URLs** — add the app's deep link: `aitouristguide://auth/callback`. Supabase only redirects to allow-listed URIs; a mismatch here is the most common setup failure (see §12).
3. **Project Settings → Data API → JWT Settings → JWT Secret** — copy this value into the backend's `SUPABASE_JWT_SECRET` (§5). This is the shared secret `app/core/security.py` uses to cryptographically verify every access token — it is **not** the same value as the anon key or the service-role key (those are themselves JWTs signed *with* this secret).

**Status as of the Phase 3 certification audit (2026-08-25): Google OAuth is NOT yet configured** in this project's Supabase dashboard (steps 1-2 above are outstanding — confirmed directly with the project owner, not assumed). This is an external, manual, dashboard-only step that cannot be performed from this repository or by an AI agent — it requires a human with access to both the Google Cloud Console and the Supabase dashboard. See `PHASE_STATUS.md`'s Phase 3 section for exactly what this blocks (the real end-to-end Google consent-screen flow) and what was validated without it (every other layer: JWT verification, protected endpoints, profile provisioning/ownership, RLS, mobile state machine — all proven with real Supabase-issued tokens obtained via the Admin API password-grant path, which does not require a configured OAuth provider).

**To unblock, a human with dashboard access must:**
1. Complete Google Cloud OAuth Client setup (§3 above) — create the OAuth client, note the Client ID/Secret.
2. Complete Supabase Auth provider setup (§4 above, steps 1-2) — enable the Google provider with those credentials, add the redirect URL allow-list entries (§8).
3. Confirm `SUPABASE_JWT_SECRET` (§4 step 3, §5) is set in `backend/.env` — required independently of Google OAuth for JWT verification to work at all.
4. Re-run `python scripts/run_live_tests.py tests/test_auth_api.py -v` to confirm the full token-verification chain, then perform one real interactive sign-in (`npx expo start --web` or a dev client) to exercise the actual consent screen.

None of the above involves a secret this repository could supply — Client Secret and dashboard configuration are inherently external to source control.

---

## 5. Environment variables

| Variable | Where | Sensitivity | Purpose |
|---|---|---|---|
| `SUPABASE_URL` | `backend/.env` | Not secret (also known to mobile) | Used to build the expected JWT issuer (`{SUPABASE_URL}/auth/v1`) and to call GoTrue's own `/logout` endpoint server-side |
| `SUPABASE_ANON_KEY` | `backend/.env` | Not secret by design | Sent as `apikey` on the backend's own call to GoTrue's `/logout` endpoint |
| `SUPABASE_SERVICE_ROLE_KEY` | `backend/.env` | **Secret** — bypasses RLS entirely | Not used by any Phase 3 code path (`app/services/auth_service.py`'s logout deliberately uses the caller's own token, not this key — see its docstring for why); reserved for future admin-only operations |
| `SUPABASE_JWT_SECRET` | `backend/.env` | **Secret** — the single most sensitive value in the system | The only thing that makes `verify_access_token()` real cryptographic verification rather than trusting an unverified claim |
| `DATABASE_URL` | `backend/.env` | **Secret** — embeds the DB password | Direct Postgres connection, full table-owner privilege (bypasses RLS) |
| `EXPO_PUBLIC_SUPABASE_URL` | `mobile/.env` | Not secret | Supabase project coordinates for the mobile Supabase client |
| `EXPO_PUBLIC_SUPABASE_ANON_KEY` | `mobile/.env` | Not secret by design (RLS is the real boundary, not this key's secrecy) | Mobile Supabase client init |
| `EXPO_PUBLIC_API_BASE_URL` | `mobile/.env` | Not secret | Backend API base URL |

**The mobile app must never receive** `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, or `SUPABASE_JWT_SECRET` — structurally enforced by these three living only in `backend/.env`, never in an `EXPO_PUBLIC_*` variable (Metro only inlines `EXPO_PUBLIC_*` names into the client bundle, so a backend-only variable can't accidentally leak into the app even by naming mistake, as long as it isn't prefixed `EXPO_PUBLIC_`).

Copy `backend/.env.example` → `backend/.env` and `mobile/.env.example` → `mobile/.env`, then fill in real values. Neither `.env` file is committed (`.gitignore`).

---

## 6. Mobile configuration

- `mobile/app.json`: `"scheme": "aitouristguide"` — registers the custom URI scheme the OS routes back to this app.
- `mobile/src/lib/supabase.ts`: creates the Supabase client with `flowType: "pkce"`, `detectSessionInUrl: false` (the app drives the redirect itself via `expo-web-browser`/`expo-linking` — there is no ambient browser URL on native to auto-detect), and a `SecureStore`-backed storage adapter (`mobile/src/lib/secureStorage.ts`).
- `mobile/index.ts`: imports `react-native-get-random-values` and `react-native-url-polyfill/auto` as its very first lines — required polyfills for `@supabase/supabase-js`'s PKCE code-verifier generation on React Native, which has neither a `crypto.getRandomValues` implementation nor a spec-compliant `URL` by default.
- `mobile/src/auth/AuthContext.tsx`: constructs the redirect URI via `Linking.createURL("auth/callback")`, which resolves to `aitouristguide://auth/callback` on a native build (and to the current web origin's equivalent path when running `expo start --web`).

---

## 7. Backend configuration

- `app/core/config.py`: `supabase_jwt_secret: SecretStr | None` — never a plain `str`; `SecretStr.__repr__`/`__str__` print `**********`, which is what prevented Incident #2 (`PHASE_STATUS.md` Phase 2) from being possible for this field.
- `app/core/security.py`: `verify_access_token()` — the sole place a token is cryptographically checked. Pins `algorithms=["HS256"]` (prevents an `alg=none`/algorithm-confusion attack — a token can't opt into a different verification path by claiming a different algorithm), checks `aud="authenticated"`, checks `iss={SUPABASE_URL}/auth/v1`, requires `exp`/`sub`/`aud`/`iss` to be present, and fails closed (raises `UnauthorizedError`) if the server itself isn't fully configured — never falls back to trusting an unverified claim.
- `app/api/deps.py`: `get_current_user()` — the only dependency any protected route uses to learn who is calling. Extracts the bearer token, delegates to `verify_access_token()`.
- `app/services/auth_service.py`: `revoke_session()` calls GoTrue's `/auth/v1/logout` using the **caller's own access token** (not the service-role key) — needs no elevated privilege, since GoTrue scopes the revocation to whichever session that token belongs to.

---

## 8. Redirect / callback configuration reference

| Environment | Redirect URI | Notes |
|---|---|---|
| Native build (dev client / production) | `aitouristguide://auth/callback` | Registered via `app.json`'s `scheme`; must also be added to Supabase's Redirect URLs allow-list (§4) |
| Expo Go | `exp://<lan-ip>:8081/--/auth/callback` (host/port vary per session) | `expo-linking`'s `createURL()` computes this automatically; must be added to Supabase's allow-list too if testing via Expo Go specifically |
| `expo start --web` | `http://localhost:8081/auth/callback` (port varies) | Used for this phase's own E2E validation path (browser automation) since no physical/simulator device is available in this environment |

Supabase's Google provider settings page also shows the fixed `https://<PROJECT_REF>.supabase.co/auth/v1/callback` URI — that one goes into **Google Cloud Console** (§3), not into this app's allow-list; the two are different links in the same chain (Google → Supabase → app).

---

## 9. Security considerations

- **No custom auth table, no passwords stored by this backend.** `auth.users`/`auth.identities` (Supabase-managed) are the only place a credential is ever held.
- **No locally fabricated JWTs anywhere** — every token in this system, in every environment including tests, originates from a real call to Supabase Auth (interactively via Google OAuth, or via the Admin API + password grant for automated integration tests — `backend/tests/test_auth_api.py`).
- **Signature, expiry, audience, and issuer are all verified** on every request — see `verify_access_token()` (§7). Verification is never disabled.
- **`user_id` is never trusted from the client.** Every `/v1/auth/*` handler resolves identity exclusively from the verified token; no route accepts a user id as input.
- **Two independent authorization layers** (application-layer scoping + RLS) — see §1. A bug in one is not automatically a full compromise, and both are exercised by real tests (`test_auth_api.py`, `test_rls_security.py`).
- **Secure on-device storage.** Native platforms use `expo-secure-store` (Keychain/Keystore-backed) — sessions never touch `AsyncStorage`, `localStorage`, or a plaintext file. The web fallback (`localStorage`) exists only for this phase's own `expo start --web` validation path, not for the shipped native product (`mobile/src/lib/secureStorage.ts`'s docstring spells this out).
- **Logout is honestly scoped.** `POST /v1/auth/logout` revokes the *refresh* token server-side; an already-issued *access* token remains cryptographically valid until its own `exp` (standard stateless-JWT behavior — Supabase access tokens are short-lived, default 1 hour). This is documented plainly in `API_SPECIFICATION.md` §2 rather than implying a stronger guarantee than is actually provided.
- **No secret is ever logged.** JWT verification failures log the exception *type* only (`app/core/security.py`); the token itself, the `Authorization` header, and the signing secret never appear in any log statement, in the mobile app's console output, or in a test assertion diff (`SecretStr` on the backend structurally prevents the last one — see the Phase 2 incident record in `PHASE_STATUS.md` for why this is written as a hard rule and not just a style preference).
- **Known operational risk to verify on a real device:** `expo-secure-store` has historically enforced a per-value size ceiling on some Android configurations. A Supabase session object (access + refresh token + user metadata) is normally well under any such limit, but this has not yet been exercised on a physical/simulator device in this phase (only via `expo start --web`, which uses the `localStorage` fallback and isn't subject to this) — worth an explicit check during first real-device testing.

---

## 10. Local testing

| Layer | Command | What it needs |
|---|---|---|
| Backend unit (JWT logic) | `pytest tests/test_security.py tests/test_deps.py` | Nothing — test-only signing secrets, no network |
| Backend integration (real Supabase tokens) | `python scripts/run_live_tests.py -k test_auth_api` | `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET` all set in `backend/.env` |
| Backend RLS (cross-user `profiles`) | `python scripts/run_live_tests.py -k test_rls_security` | `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` |
| Mobile unit (state machine, screens) | `npm test` (in `mobile/`) | Nothing — Supabase client fully mocked, test-only fake `EXPO_PUBLIC_*` values from `jest.setup.js` |
| Full mobile app, manual | `npx expo start --web` (or a dev client) | Real `mobile/.env` values; Google OAuth configured in Supabase (§4) for the consent screen itself to work |

Never run any of these against production credentials.

---

## 11. Production considerations (not yet implemented — flagged for later phases)

- **Custom domain for the Supabase Auth callback**, so the redirect URI a user sees during consent reflects the product's own domain rather than `*.supabase.co` — a Supabase Pro-tier feature, out of scope for this phase's local/dev setup.
- **EAS Build deep-link registration** — a production native build needs the `aitouristguide://` scheme registered with the OS at the platform level (`app.json`'s `scheme` handles this for Expo-managed builds; a bare/prebuild workflow would need explicit `Info.plist`/`AndroidManifest.xml` entries).
- **JWT secret rotation** — rotating `SUPABASE_JWT_SECRET` invalidates every currently-issued access token instantly (they fail signature verification) — needs a coordinated rollout (mobile clients re-authenticate), not just a backend config change. Not exercised in this phase.
- **Rate limiting on auth endpoints** specifically (`API_SPECIFICATION.md` §1 already specifies general rate limiting; auth endpoints deserve tighter limits given their sensitivity) — not implemented this phase.

---

## 12. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `GET /v1/auth/me` → `401 Authentication is not configured on this server.` | `SUPABASE_JWT_SECRET` (or `SUPABASE_URL`) unset in `backend/.env` | Set it from the Supabase dashboard (§4); the server fails closed rather than trusting an unverifiable token |
| `GET /v1/auth/me` → `401 Invalid or expired authentication token.` immediately after a real sign-in | Clock skew between device and server (rare), or the token really is from a different Supabase project | Check `iss` on the token payload matches this project's `{SUPABASE_URL}/auth/v1` exactly |
| Google consent screen loads but redirect back to the app never happens / browser hangs | Redirect URI not in Supabase's allow-list (§4/§8), or a mismatch between the exact URI `signInWithOAuth` requested and what's allow-listed | Add the exact URI `Linking.createURL("auth/callback")` produces for your current environment (native vs Expo Go vs web all differ — §8) |
| `exchangeCodeForSession` fails with an invalid-grant-style error | The authorization code was already used (e.g., a duplicate redirect fire), or too much time elapsed | Retry sign-in from the start; codes are single-use and short-lived by design |
| Mobile app crashes at startup with "Missing required environment variable EXPO_PUBLIC_SUPABASE_URL" | `mobile/.env` missing or incomplete | Copy `mobile/.env.example` → `mobile/.env` and fill in both Supabase values (§5) — this is a deliberate loud failure, not a bug, since the app cannot function without them |
| A backend test in `test_auth_api.py`/`test_rls_security.py` is silently skipped | One or more of `DATABASE_URL`/`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_ANON_KEY`/`SUPABASE_JWT_SECRET` isn't set | Expected/by design when credentials aren't configured (§10) — never "fake" these tests into passing without real credentials |

---

## 13. Development Setup — Step-by-Step Checklist

For a new machine/environment picking this project up:

1. **Supabase project** — already provisioned (Phase 2); obtain its `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` from the Supabase dashboard (Project Settings → Data API / Database) if you don't already have them.
2. **JWT secret** — Project Settings → Data API → JWT Settings → JWT Secret → set as `SUPABASE_JWT_SECRET` (§4 step 3).
3. Copy `backend/.env.example` → `backend/.env`, fill in all five values above. Never paste real credentials into a chat/terminal transcript that isn't your own local shell — this project has a documented incident (`PHASE_STATUS.md` Phase 2) from exactly that mistake.
4. Copy `mobile/.env.example` → `mobile/.env`, fill in `EXPO_PUBLIC_SUPABASE_URL` / `EXPO_PUBLIC_SUPABASE_ANON_KEY` (same project, public-safe values) and `EXPO_PUBLIC_API_BASE_URL`.
5. `cd backend && pip install -e ".[dev]"` then `python -m pytest -v` — should pass with the live-database/RLS/auth-API suites reported `SKIPPED` (they require the env vars to be in the **process environment**, not just `backend/.env` — see §10 above and use `python scripts/run_live_tests.py` to run them for real).
6. `cd mobile && npm install` then `npm test` — should pass entirely offline (Supabase client is mocked in tests, `jest.setup.js` supplies fake config).
7. **Google OAuth** (§3-4) — only required to exercise the actual interactive consent screen; every other layer (JWT verification, protected endpoints, RLS) is fully testable without it via the Admin API password-grant technique `test_auth_api.py`/`test_rls_security.py` use.
8. `cd backend && uvicorn app.main:app --reload` + `cd mobile && npx expo start --web` to run the real app locally.

## 14. Production Setup Checklist

Beyond §11's flagged production considerations:

1. A dedicated Supabase **production project**, separate from the dev/staging project used above (`DEPLOYMENT_PLAN.md` §1) — never share a database between environments.
2. Google OAuth client and Supabase provider configuration (§3-4) repeated against the production project's own credentials and redirect URIs — a production Google OAuth client is a distinct Google Cloud Console entry from any dev/test client.
3. All five backend secrets (§5) supplied via the hosting platform's secret store (`DEPLOYMENT_PLAN.md` §4), never baked into the container image.
4. EAS Secrets configured for the mobile `production` build profile with the production project's public Supabase coordinates (`DEPLOYMENT_PLAN.md` §3.3).
5. Rate limiting on `/v1/auth/*` (§11 — not yet implemented) should be in place before production traffic, given auth endpoints are a standard abuse target.
6. A real backup/restore test of the Supabase production project (`DEPLOYMENT_PLAN.md` §9) before launch — `profiles` and `auth.users` are the most consequential tables to lose.
