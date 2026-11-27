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

## 019 - The methodology library is curated data with a strict schema, not model output
Methods live as one YAML file per method and are validated on load: strong or moderate evidence
requires a source, methods for low_energy or burnout_risk require an escalation note, steps and
contraindications are mandatory, unknown fields are rejected and the slug must match the file
name. A broken file fails loudly with its file name. The model will later be allowed to pick from
this library but never to write a method, so every suggestion can be traced to a reviewed source.

## 020 - Honest evidence levels and human review dates
Each method states strong, moderate, limited or practitioner evidence with a note on its limits,
because much self-improvement advice has weak research behind it and users should not be told
otherwise. `reviewed_on` records when a person checked the citations, and the coverage report lists
methods nobody has reviewed yet.

## 021 - Retrieval filters by roadblock first, then ranks
Candidates are the methods whose targets include a detected roadblock, found with a plain code
filter that cannot be fooled by wording. Ranking is the number of matched roadblocks, then text
similarity, then stronger evidence, then slug, so results are explainable and deterministic. The
model never chooses from outside the library, and only a few methods are returned because too
many options make people do nothing.

## 022 - A local hashing embedder behind an interface, with two stores
The embedder is free, deterministic and offline, which keeps tests fast and avoids sending user
text to a third party for now. It matches words, not meaning, and the eval shows the cost: one
planning case ranks second. Storage has an in-memory backend for tests and a pgvector backend for
Postgres. The vector table is created by a hand-written migration and excluded from autogenerate,
because the vector type does not exist on the SQLite used in unit tests. Postgres tests are
skipped unless TEST_POSTGRES_URL is set, refuse to run against a database not ending in _test,
and run in CI against a real pgvector container. The column is fixed at 256 dimensions, so a
real embedding model with another size will need a new migration.

## 023 - Migration history is guarded by tests
`alembic revision` creates a new file on every run, and running it three times produced three
migrations that each created the same table, which broke `upgrade head`. Tests now require
exactly one migration head, a linear history with a single base, and the pgvector table created
by exactly one migration. The Postgres tests also build a fresh database from the migrations, and
CI runs them against a real pgvector container, so a broken chain fails before it merges.

## 024 - Roadblocks come from data rules and verified quotes, never from the model alone
Activity data is judged by plain rules whose thresholds are documented and tested at their
boundaries, and they are skipped when there is too little data. The model may only propose
roadblocks from the taxonomy; unknown ids are dropped and reported. A model suggestion counts as
strong only if its quote really appears in the user's text; otherwise it is a "possible" guess,
clearly labelled. Rules and words are merged per roadblock, so a roadblock backed by both shows
both signals. Known gaps: a quote can exist inside an injected instruction, and only 6 of the 9
roadblocks have a rule, because the other 3 have no data to judge from yet.

## 025 - Sensitive roadblocks carry a fixed care note, and the data path survives model failure
Energy and burnout results always come with a fixed, code-written note that these are signals
from the user's own entries and not a diagnosis, with a pointer to a doctor or counsellor.
The note is not model-written. The crisis check runs first on any text, and a trigger skips
detection entirely. If the model is down but activity data was sent, the data-based results are
still returned with a note, because a model outage should not erase information we can compute.
The activity summary is supplied by the client for now; the server will compute it from stored
plans and check-ins in Weeks 4 and 5.

## 026 - Method selection is rule-based, history-aware and capped
Suggestions come only from the reviewed library, through the same filter-then-rank retrieval,
so every suggestion traces to a source and costs nothing to produce. At most two are returned,
because choice overload makes people do nothing. A user's own history reshapes the list: methods
they are already trying are excluded, abandoned or poorly rated ones go last (and are only shown
with an explanation when nothing else fits), and methods they rated highly are marked. The most
recent finished attempt decides, so a method abandoned once and later loved is not punished.

## 027 - Experiments are structured, capped and race-safe
An experiment records only the method, roadblock, status and a 1 to 5 rating, with no free text,
because free text must pass the crisis check and that arrives with check-ins. A user may have at
most a few active experiments, which protects against over-planning, and may not run the same
method twice at once. That rule is enforced by a partial unique index in the database, not just
by code, so two simultaneous requests cannot both succeed. The method is stored as a slug and not
as a foreign key because methods live in files; experiments for a removed method still list, with
no title. Export and account deletion were extended in the same change.

## 028 - The end-to-end eval scripts the model and checks what the code does with its output
Each golden case scripts what the model says, including wrong things: an invented roadblock, a
quote that is not in the text, an instruction hidden inside the user's words, a model that is
down. The cases then assert the final roadblocks, their strength and the suggested methods. This
tests the verification layers, which are the part we wrote, rather than the model's answers,
which we do not control. Safety is checked first in every case: a crisis text must stop the chain
with no model call, no roadblocks and no methods.

## 029 - Invariants are checked on every combination, not just on examples
Besides golden cases, the eval asks for methods for all 255 combinations of one to four
roadblocks, with and without a description, and checks the same rules each time: at most two
suggestions, no duplicates, every method in the library, matched roadblocks only from the
request, reasons and contraindications present, escalation notes on energy and burnout methods,
and the care note present exactly when such a method is shown. It also fails if any combination
gets no suggestion, so removing the last method for a roadblock is caught in CI. Known gap:
goal titles and descriptions are the remaining free-text fields that are not yet screened by the
crisis check; check-ins in Week 5 must use the same safety function.

## 030 - The scheduler is built on whole-minute half-open intervals
Plans are checked and built with plain integer minutes after midnight, as [start, end) ranges. Touching
blocks are not a conflict. There are no time zones, floats or datetimes inside the scheduler, so the
rules ("no overlap", "inside capacity") are exact and easy to test. Conversion to real dates happens
only at the edges. Why this matters: ___ (rewrite in your own words).

## 031 - The model never picks times; code does
The model may suggest which tasks matter and how long they take, but only code places them on the
clock. Tasks, blocks and the day's context are validated plain objects, and the same rules are used
to build a plan and to check one. Why this matters: ___ (rewrite in your own words).

## 032 - A task is placed whole or not at all, and the plan says what it dropped
The scheduler never silently shrinks, overlaps or hides a task. A task that cannot fit is returned in
an `unplaced` list with a reason (over the focus limit, or no free time). Long focus work is split
into pieces with breaks. Why this matters: ___ (rewrite in your own words).

## 033 - Greedy earliest-fit instead of an optimiser
Tasks are tried by priority and placed at the earliest gap that fits. This is not the best possible
packing, but it is predictable, explainable to the user, and the same input always gives the same
plan. A smarter optimiser can replace it later without changing the rules it must satisfy.
Why I chose this: ___ (rewrite in your own words).

## Known gaps (scheduler)
- Placement is earliest-fit, so mornings fill first even if the user focuses best in the evening.
- No task dependencies or "must finish by" times yet.
- A break is only added when there is room for a full one after the piece.

## 034 - A separate validator checks every plan
The scheduler builds plans; a different module re-checks them from the finished blocks only (no
shared placement code). So a bug in the scheduler, a plan loaded from storage, or a hand-edited plan
is still caught before the user sees it. A random sweep requires the scheduler to pass its own
referee on 500 generated days. Why this matters: ___ (rewrite in your own words).

## 035 - A bad day gets a smaller plan, not a failed one
When the full plan cannot fit a must-do task, or the user asks for a lighter day, the system switches
to a minimum viable day: at most two tasks, each cut to a 30-minute first step, half the focus
limit. Every dropped or shrunk task is listed with a reason. Why this matters: ___ (rewrite in your
own words, and link it to the minimum_viable_day method in the library).

## 036 - Fallback output is validated against what it actually planned
A minimum viable day changes the tasks and the focus limit, so the plan carries the reduced tasks and
context it was built from. The validator checks the plan against those, and the fallback calls it
before returning. Why this matters: ___ (rewrite in your own words).

## 035 - A bad day gets a smaller plan, not a failed one
When the full plan cannot fit a must-do task, or the user asks for a lighter day, the system switches
to a minimum viable day: at most two tasks, each cut to a 30-minute first step, half the focus
limit. Every dropped or shrunk task is listed with a reason. Why this matters: ___ (rewrite in your
own words, and link it to the minimum_viable_day method in the library).

## 036 - Fallback output is validated against what it actually planned
A minimum viable day changes the tasks and the focus limit, so the plan carries the reduced tasks and
context it was built from. The validator checks the plan against those, and the fallback calls it
before returning. Why this matters: ___ (rewrite in your own words).

## 037 - The planner has its own eval, and the eval can fail
Planning is gated like the model-based parts: hand-worked golden days, ten ways of corrupting a plan
that the validator must notice, and a 1000-day random sweep. Tests prove the eval goes red if the
validator is blinded or the planner loses a task. Why this matters: ___ (rewrite in your own words,
and say why a check that cannot fail is worthless).

## 038 - Plans are stored as plain rows and re-validated on every load
The plan-to-rows conversion is ordinary Python with no database in it, so it is tested heavily on
its own (including a 300-day random sweep and damaged-row tests). Loading a plan rebuilds it and
runs the validator again, so a plan that was edited or corrupted in storage is rejected instead of
shown. Why this matters: ___ (rewrite in your own words).

## 039 - The database also enforces the basic rules
Check constraints reject a block that ends before it starts or leaves the day, one plan per user per
day is a unique constraint, and every plan query is scoped to the user. The code checks the same
rules, so a bug in either layer is caught by the other. Why I want both: ___ (rewrite in your own words).

## Known gaps (plan storage)
- Account export and delete do not call the plan functions yet (Day 8). Until then, deleting a user
  relies on the foreign key cascade in the database.
- One plan per user per day; earlier versions of a regenerated plan are not kept.

## 040 - The plan API never calls a model and rejects bad input before planning
A plan request is validated at the edge (times, ranges, unique keys, overlapping fixed blocks) and
converted to the planner's own objects inside the request model, so anything the planner would reject
is an ordinary 422. Planning itself is deterministic code, so no model call, rate limit or crisis check
is involved. Why this matters: ___ (rewrite in your own words).

## 041 - Another user's plan looks like a plan that does not exist
Every plan query is scoped to the signed-in user, and a plan or goal that belongs to someone else
returns 404, not 403, so the API does not reveal which plans exist. Same rule as goals and
experiments. Why this matters: ___ (rewrite in your own words).
