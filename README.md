# AI Life Orchestrator

Backend for a personal life-orchestration system: Life Model -> roadblocks -> methods -> a
constraint-checked daily plan. **Week 1 scope:** auth, goals hierarchy, schedule constraints,
migrations, tests, CI.

## Quick start (Docker)

```bash
cp .env.example .env          # optional for Docker, required for local runs
docker compose up --build     # starts Postgres (pgvector) + API, runs migrations
```

API docs: http://localhost:8000/docs

## Local development (without Docker for the API)

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
docker compose up -d db                                # just the database
alembic revision --autogenerate -m "initial schema"    # first time only, then review the file
alembic upgrade head
uvicorn app.main:app --reload
```

## Checks

```bash
pytest -q
ruff check .
```

## Endpoints (Week 1)

| Method | Path | Purpose |
|---|---|---|
| POST | /auth/register | create account (consent required) |
| POST | /auth/login | get bearer token |
| GET | /auth/me | current user |
| POST/GET | /goals | create / list (filters: horizon, status, parent_id) |
| GET/PATCH/DELETE | /goals/{id} | read / update / delete |
| POST | /goals/{id}/review | confirm goal still valid |
| POST/GET | /constraints | create / list (filters: kind, active) |
| GET/PATCH/DELETE | /constraints/{id} | read / update / delete |
| GET | /health, /health/ready | liveness / readiness |

Design notes live in `docs/decisions.md`.
