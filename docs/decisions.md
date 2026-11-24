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

## 008 - Goal tree built in Python from one query
GET /goals/tree loads all of a user's goals in one query and builds the tree in memory with a
dict keyed by goal id. This avoids one query per level and a recursive SQL query, and a user's
goal count is small. A goal whose parent is missing is treated as a root, so a broken link never
hides data. The route is declared above /{goal_id} so "tree" is not parsed as a goal id.

## 009 - Account deletion deletes child rows explicitly
DELETE /auth/me removes the user's goals and constraints in code before deleting the user,
instead of relying only on ON DELETE CASCADE. Tests run on SQLite, which does not enforce
foreign keys by default, so a cascade-only implementation passed in Postgres but left orphaned
rows in the test database. Explicit deletes behave the same everywhere. The export endpoint
returns the user's own data only and never includes the password hash.

## 010 - LLM access behind a provider interface with validated structured output
All model calls go through `LLMProvider` (fake and Anthropic adapters). `complete_structured`
asks for JSON that matches a Pydantic schema, validates it, and retries once with the validation
error. Nothing the model returns is used until it passes validation, which keeps the LLM in the
"proposes" role. The fake provider makes every test free and deterministic, and the provider is
chosen by environment variable so switching vendors needs no code change in features.

## 011 - Life Model stored as immutable versions with provenance
Each save appends a new row (user_id + version, unique together) instead of updating one. The
current model is the highest version, and history supports the "view and correct your memory"
requirement and later "what changed" features. Each item is tagged stated, belief or inferred,
with an optional quote of the user's own words, so the model's guesses can never pass as facts.
LifeModelData rejects unknown fields so a model cannot slip in data we do not expect.

## 012 - LLM call log stores metadata only
`llm_calls` keeps provider, model, prompt version, attempts, tokens, latency and a truncated
error, but never prompt or response text, because those contain personal life details. A test
asserts the table has no text columns. Account export and deletion were extended to cover the
new tables, and a comment in the delete route reminds future changes to do the same.
