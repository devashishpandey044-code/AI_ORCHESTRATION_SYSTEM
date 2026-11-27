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

## AI quality checks

```bash
python -m app.evals.grounding
```

Runs golden cases through the onboarding grounding check (a "stated" item must quote the
user's own words) and reports the catch rate for invented items and the false-downgrade rate
for genuine ones. It also lists known gaps, which are tracked in code but not in the gate.
CI runs it on every push.

## Safety check

Free text goes through a deterministic crisis check before any model is called. If it triggers,
the API returns fixed support information (region set by `CRISIS_REGION`) and nothing is sent
to a model or saved. `python -m app.evals.safety` reports recall on risk statements and false
positives on everyday phrases; CI runs it. This is a baseline, not a clinical tool: it misses
indirect wording (tracked in `app/evals/safety_cases.py`), and the message and contact numbers
must be reviewed by a qualified person and re-verified before real users.

## Week 2 endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | /onboarding/propose | safety check, then the model proposes a Life Model from the user's text (saves nothing) |
| POST | /onboarding/confirm | save what the user approved as a new version (no model involved) |
| GET | /life-model | current Life Model |
| PUT | /life-model | user edit, saved as a new version (unchanged edits create nothing) |
| GET | /life-model/versions | version history |
| GET | /life-model/versions/{n} | one version |
| POST | /life-model/versions/{n}/restore | copy an old version into a new one |
| GET | /auth/me/export | now includes Life Model versions |

## Running with a real model

Default is a free fake provider. To use a real one, set these in `.env` (never commit it) or in
Codespaces secrets: `LLM_PROVIDER=anthropic`, `LLM_MODEL=<model id>`, `ANTHROPIC_API_KEY=<key>`.

## Quality checks

```bash
pytest -q
ruff check .
python -m app.evals.grounding   # invented goals are caught
python -m app.evals.safety      # crisis check recall and false positives
```

## Method retrieval

```bash
python -m app.retrieval.demo --roadblocks distraction --text "my phone keeps buzzing"
python -m app.retrieval.index        # embed the library into Postgres (pgvector)
python -m app.evals.retrieval        # golden retrieval cases
```

Retrieval filters methods by roadblock, then orders by how many roadblocks match and text
similarity. The embedder is a local word-based hashing embedder (lexical, not semantic) behind
an interface so a real embedding model can replace it. Postgres tests run when
`TEST_POSTGRES_URL` points at a database whose name ends in `_test`.

## Roadblock detection

`POST /roadblocks/detect` takes the user's words and/or a summary of recent activity and returns
the roadblocks it found, each with its signals. Activity data is checked by plain rules with
documented thresholds; the model reads the words but must quote them, and code checks the quote
really is in the text. `python -m app.evals.roadblocks` runs golden cases for both. This is a
signal, not a diagnosis: energy-related results always carry a care note.

Local manual testing: `TOKEN=$(bash scripts/token.sh)`, then post a file from `scripts/samples/`.
The token script uses a throwaway local dev account; never put real credentials in the repo.

## Git workflow (read this when the test count looks wrong)

- Never edit or commit on `main`. Start every change with `bash scripts/new-branch.sh feature/name`.
- `bash scripts/doctor.sh` shows whether your copy is behind GitHub or on the wrong branch.
- After a pull request is merged, run `bash scripts/sync-main.sh`, then `bash scripts/doctor.sh`.
- `bash scripts/check.sh` runs everything CI runs. The count in GitHub Actions on `main` is the truth.
- In every new Codespace, run `bash scripts/setup-git.sh` once.
