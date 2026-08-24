# AI Personalized Tourist Guide & Travel Companion (TC-SO1)

Production-oriented mobile travel companion — see `docs/AI_Tourist_Guide_Master_PRD_SDLC.pdf` for the full product spec and `CLAUDE.md` for the binding engineering rules governing this repository.

**Status: Phase 1 (Project Foundation) in progress.** No product features are implemented yet — see `docs/PHASE_STATUS.md` for the current, authoritative build state.

## Documentation

Read before contributing anything:

| Doc | Purpose |
|---|---|
| `docs/AI_Tourist_Guide_Master_PRD_SDLC.pdf` | Product source of truth |
| `docs/IMPLEMENTATION_BLUEPRINT.md` | Feature-by-feature plan, phase roadmap |
| `docs/DATABASE_SCHEMA.md` | Schema, RLS, migrations |
| `docs/API_SPECIFICATION.md` | Endpoint contracts |
| `docs/AI_ARCHITECTURE.md` | AI/RAG pipelines |
| `docs/MOBILE_ARCHITECTURE.md` | Client architecture |
| `docs/DEPLOYMENT_PLAN.md` | Environments, CI/CD, ops |
| `docs/TESTING_PLAN.md` | Test strategy per layer |
| `docs/ARCHITECTURE_REVIEW.md` | Open audit findings — check before touching a flagged area |
| `docs/PHASE_STATUS.md` | What has actually been built, phase by phase |
| `CLAUDE.md` | Binding engineering rules for this repository |

## Repository Structure

```
/
├── mobile/     React Native + Expo client
├── backend/    FastAPI service
├── database/   Migrations and schema-related tooling
├── scripts/    One-off / operational scripts
├── tests/      Cross-cutting integration & E2E tests (backend unit/integration tests live in backend/tests; mobile tests live in mobile/)
└── docs/       Product & engineering documentation
```

## Backend — Local Development

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"
copy .env.example .env        # fill in real values locally, never commit .env
uvicorn app.main:app --reload
```

Health check: `GET http://localhost:8000/healthz`
Interactive API docs: `http://localhost:8000/docs`

Run tests: `pytest`
Lint: `ruff check .`
Format check: `black --check .`
Type check: `mypy app`

## Mobile — Local Development

```bash
cd mobile
npm install
copy .env.example .env        # fill in real values locally, never commit .env
npm start
```

Type check: `npm run typecheck`
Lint: `npm run lint`
Tests: `npm test`

## Environment Variables

See `.env.example` (root), `backend/.env.example`, and `mobile/.env.example`. Placeholders only — never commit real secrets (`CLAUDE.md` §4).
