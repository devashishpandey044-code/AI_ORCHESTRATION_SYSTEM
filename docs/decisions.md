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

## 013 - Propose, verify, confirm: the model never writes the Life Model
`/onboarding/propose` asks the model for a structured proposal but saves nothing. A deterministic
check then requires every "stated" or "belief" item to quote the user's own words; anything that
cannot be found in the text is downgraded to "inferred" and reported. `/onboarding/confirm`
saves exactly what the user sends back, with no model involved, so the user can edit first. This
keeps the LLM in the "proposes" role. Known gap: `current_situation` has no provenance, so the
user's confirmation is its only check.

## 014 - Prompt-injection and cost controls on the onboarding call
The user's text is wrapped in delimiters, copies of the delimiters are stripped from it, and the
system prompt says the text is data. Each user is limited to a fixed number of onboarding calls
per rolling 24 hours (counted from `llm_calls`, including failures), and a failed call returns a
generic error that never echoes the user's text.

## 015 - Life Model edits and restores never rewrite history
`PUT /life-model` saves the user's edited copy as a new version (source: user_edit), with no
model involved. An edit that changes nothing creates no version. Restoring an old version copies
it into a new one, so every state stays retrievable. Two saves racing for the same version
number are stopped by the unique (user_id, version) constraint and returned as a 409 instead of
a 500. Version numbers in URLs are bounded so a huge number cannot overflow a database integer.

## 016 - Golden eval for the grounding check, with known gaps tracked in code
`python -m app.evals.grounding` runs labelled cases and reports how many invented items were
caught and how many genuine items were wrongly downgraded; CI fails if either is not perfect.
Three known weaknesses are recorded as cases outside the gate and pinned by a test: a quote that
exists inside an injected instruction, a real quote that does not support the item, and a
paraphrased quote that is downgraded. The user's confirmation step remains the final control.

## 017 - Safety check runs first, deterministically, before any model call
`/onboarding/propose` checks the text for self-harm risk before length rules, rate limits or any
LLM call. A trigger returns a fixed message and support contacts and does nothing else: no model
call, no `llm_calls` row, no saved data, and it does not use up the daily limit. The check was
moved ahead of the 20-character minimum after noticing the minimum would have rejected the
shortest, most direct messages before they were ever checked. Rules are simple regexes (English,
Hindi, romanised Hindi) because they are fast, free, predictable and testable. They are a floor:
indirect statements are missed, tracked as known gaps, and there is no "continue anyway" bypass
yet.

## 018 - Safety events are anonymous, and contacts are data
`safety_events` stores the surface and rule ids that fired, with no user id and no text, so the
fact that someone wrote something sensitive is not tied to an account. Trade-off: no follow-up
and little analysis per user. Support contacts live in one file with a verified-on date per
region, and a test asserts the India entry includes Tele-MANAS and 112. Known gap: other
free-text fields (goal titles and descriptions) are not checked yet; the daily check-in in
Week 5 must call the same function.
