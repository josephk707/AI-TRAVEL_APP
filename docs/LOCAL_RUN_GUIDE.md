# Local Run Guide — AI-TRAVEL_APP (Yatra AI)

Step-by-step record of how the app was brought up on a Mac on 2026-09-06.
The app has two processes that must both run:

| Process | Tech | Port | URL |
|---|---|---|---|
| Backend API | FastAPI + uvicorn | 8000 | http://localhost:8000 (docs: `/docs`, health: `/healthz`, readiness: `/readyz`) |
| Mobile / web client | Expo SDK 57 + react-native-web | 8081 | http://localhost:8081 |

The client calls the backend at `EXPO_PUBLIC_API_BASE_URL` (set to `http://localhost:8000` in `mobile/.env`).

---

## 0. Prerequisites (what was present on the machine)

| Tool | Version used | Notes |
|---|---|---|
| Python | 3.12.13 (`python3.12`, Homebrew) | Default `python3` was 3.14; 3.12 was chosen for the venv because it has the widest wheel support. |
| Node / npm | 26.5.0 / 11.17.0 | |
| Env files | `backend/.env`, `mobile/.env` | Already filled in. Never commit them. If missing, copy from the `.env.example` files. |

Check quickly:

```bash
python3.12 --version
node -v && npm -v
ls backend/.env mobile/.env
```

---

## 1. Backend (FastAPI)

### 1.1 Create the virtual environment and install

```bash
cd ~/Desktop/AI-TRAVEL_APP/backend
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install --prefer-binary -e ".[dev]"
```

`.[dev]` installs the app plus pytest, ruff, black, mypy. `.venv/` is git-ignored.

### 1.2 Start the server

```bash
cd ~/Desktop/AI-TRAVEL_APP/backend
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Expected log lines:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
... message="ai_provider_configured provider=gemini gemini_configured=YES ..."
... message="db_pool_created"
INFO:     Application startup complete.
```

### 1.3 Verify

```bash
curl -s http://localhost:8000/healthz
# {"data":{"status":"ok","app_name":"TC-SO1 Backend","app_version":"0.1.0","environment":"development"},"meta":null}

curl -s http://localhost:8000/readyz
# {"data":{"status":"ready","checks":{"config":"ok","database":"ok","schema_status":"ok"}},"meta":null}
```

If `database` is not `ok`, check `DATABASE_URL` in `backend/.env`.

---

## 2. Mobile / Web client (Expo)

### 2.1 Install dependencies

```bash
cd ~/Desktop/AI-TRAVEL_APP/mobile
npm install --no-audit --no-fund
```

Do **not** use `npm ci`. It fails with:

```
npm error `npm ci` can only install packages when your package.json and package-lock.json ... are in sync.
npm error Missing: @emnapi/core@1.11.2 from lock file
```

The lockfile was generated on Windows and lacks three optional macOS packages. `npm install` adds them and modifies `package-lock.json`; that diff is expected.

### 2.2 Make sure port 8081 is free

The backend's CORS allow-list (`CORS_ALLOW_ORIGINS` in `backend/.env`) only permits `http://localhost:8081` and `http://localhost:19006`. The web client therefore **must** be served on 8081, or every API call from the browser is blocked.

```bash
lsof -iTCP:8081 -sTCP:LISTEN        # shows any process holding the port
kill <PID>                          # e.g. a Metro bundler from another React Native project
```

### 2.3 Start the Expo dev server

```bash
cd ~/Desktop/AI-TRAVEL_APP/mobile
npx expo start --port 8081
```

Expected log lines:

```
env: load .env
env: export EXPO_PUBLIC_API_BASE_URL EXPO_PUBLIC_GOOGLE_MAPS_SDK_KEY EXPO_PUBLIC_SUPABASE_ANON_KEY EXPO_PUBLIC_SUPABASE_URL
Starting Metro Bundler
Waiting on http://localhost:8081
```

Do **not** prefix the command with `CI=1`. That puts Metro in CI mode and disables file watching / hot reload.

From the same terminal you can press `w` to open the web build, `a` for the Android emulator, or scan the QR code with Expo Go on a phone.

### 2.4 Verify

Open http://localhost:8081 in a browser. The first load bundles for web (about 10 to 20 seconds). The page title becomes `InterestSelect` and the onboarding screen "What excites you?" appears with the interest chips and a Continue button.

The Expo terminal should show:

```
Web  LOG  Running application "main" with appParams: {"hydrate": undefined, "rootTag": "#root"}
```

Warnings about `expo-notifications` on web and deprecated `shadow*` style props are expected and harmless.

---

## 3. Everyday restart (after the one-time setup above)

Terminal 1:

```bash
cd ~/Desktop/AI-TRAVEL_APP/backend && .venv/bin/uvicorn app.main:app --reload
```

Terminal 2:

```bash
cd ~/Desktop/AI-TRAVEL_APP/mobile && npx expo start --port 8081
```

Then open http://localhost:8081.

---

## 4. Stopping

Press `Ctrl+C` in each terminal. If a server was started in the background:

```bash
lsof -iTCP:8000 -sTCP:LISTEN   # uvicorn
lsof -iTCP:8081 -sTCP:LISTEN   # expo / metro
kill <PID>
```

---

## 5. Problems hit during the first run and their fixes

| Symptom | Cause | Fix |
|---|---|---|
| `npm ci` exits with EUSAGE, "Missing: @emnapi/core ... from lock file" | Lockfile created on Windows, missing optional macOS packages | Use `npm install` (README's own instruction) |
| Browser API calls blocked / CORS errors | Expo served on a port other than 8081 | Free 8081 and start Expo with `--port 8081`, or add the port to `CORS_ALLOW_ORIGINS` |
| "Metro is running in CI mode, reloads are disabled" | Expo started with `CI=1` in the environment | Start it without `CI` set |
| Expo prints "An update for expo is available: 57.0.15 → ~57.0.20, 12 other packages may need updating" | Minor version drift within SDK 57 | Optional: `npx expo install --check` |
