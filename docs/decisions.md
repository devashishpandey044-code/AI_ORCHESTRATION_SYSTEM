# Architecture decisions (running log)

Add one entry per real trade-off. Interviewers love this file.

## 001 - Sync SQLAlchemy 2.0 + psycopg3
Simpler to reason about and test than async for a CRUD-heavy v1. LLM calls (Week 2+) are the slow
part and will be isolated behind the `llm/` wrapper, so async DB access buys little yet.

## 002 - JWT bearer auth with Argon2id password hashing
Stateless auth is enough for v1. Argon2id is the current recommended password hash. Login does a
dummy hash verification for unknown emails to avoid leaking which emails exist via timing.
Trade-off: register returns 409 on duplicate email (reveals existence) - accepted for UX in v1.

## 003 - Per-user scoping on every query; 404 instead of 403
All reads/writes filter by `user_id`. Another user's resource is reported as not found so IDs
cannot be probed. Covered by cross-user tests for every resource.

## 004 - Goal hierarchy validated in the API layer
Vision > milestone > weekly > daily; a child must sit strictly below its parent. Horizon is not
editable after creation, which keeps the hierarchy valid without recursive checks.

## 005 - Goals carry `source`, `confidence`, `last_reviewed_at`
Directly supports the blueprint's "goal lock-in" risk and the eval "does it preserve the user's
actual goals rather than inventing them" (stated vs inferred).

## 006 - Enums stored as VARCHAR, not native PG enums
Avoids painful `ALTER TYPE` migrations as the taxonomy evolves.

## 007 - Tests run on in-memory SQLite (for now)
Fast feedback. Known gap: Postgres-specific behaviour is not covered. Add a Postgres service to CI
once pgvector queries arrive in Week 3.
