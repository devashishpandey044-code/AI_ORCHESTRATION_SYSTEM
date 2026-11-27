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

## 040 - The plan API never calls a model and rejects bad input before planning
A plan request is validated at the edge (times, ranges, unique keys, overlapping fixed blocks) and
converted to the planner's own objects inside the request model, so anything the planner would reject
is an ordinary 422. Planning itself is deterministic code, so no model call, rate limit or crisis check
is involved. Why this matters: ___ (rewrite in your own words).

## 041 - Another user's plan looks like a plan that does not exist
Every plan query is scoped to the signed-in user, and a plan or goal that belongs to someone else
returns 404, not 403, so the API does not reveal which plans exist. Same rule as goals and
experiments. Why this matters: ___ (rewrite in your own words).

## 042 - A guard test makes account export and delete cover every user table

**Context:** Adding the plans tables meant account export and delete had to change, and nothing forced that. A forgotten table would leave a user's data behind after deletion.

**Decision:** A test lists every table with a foreign key to users and fails unless the account code calls the handler for it (a helper function where one exists, otherwise the model class name).

**Why:** The mistake is silent and privacy-relevant, so the build should fail instead of relying on memory. The first version passed on an import alone, so the test now requires an actual call.

**Trade-off:** A new table needs a one-line entry in the test when it uses a helper. That is intended friction.

## 043 - Adherence counts planned minutes only; overruns are tracked separately

**Context:** A check-in can report more time on a task than planned. Counting it would let one long task hide a skipped one.

**Decision:** Each task counts at most its planned minutes toward adherence. Extra minutes are recorded as overrun. Tasks the user did not report are listed and count as zero. Percentages use integer maths, rounded half up.

**Why:** Adherence should answer "how much of the plan happened", and overruns are a separate signal (the user underestimates), useful for suggesting longer estimates later.

**Trade-off:** A user who finishes everything and then some shows 100%, not more. That is intended.

## 044 - A roadblock needs repetition across days, and is ranked by minutes lost

**Context:** The system should name what keeps blocking the user, but a single bad day says little.

**Decision:** A reason counts as a roadblock only after at least 3 occurrences on at least 2 different days (both adjustable). Roadblocks are ranked by planned minutes lost, with ties broken by count and then by reason name, so output is deterministic. Estimation bias is reported separately, from finished tasks only.

**Why:** Fixing the biggest recurring cost first helps most, and partial tasks would distort the estimate because they were cut short.

**Trade-off:** A new user needs a few days of data before any pattern appears. Showing nothing is better than guessing from one day.

## 045 - Weekly suggestions come from fixed rules, not a model

**Context:** The weekly review must tell the user what to change. A model could write it, but then the advice could not be tested, and it could contradict the data.

**Decision:** Suggestions are chosen by thresholds in code (under 60% adherence plans less, 125% or more estimate ratio lengthens estimates, 30% or more unreported asks for more check-ins, and so on). Each has a fixed message and the number it is based on. With fewer than 3 days of data the only suggestion is to keep checking in.

**Why:** Every suggestion can be traced to a number, tested, and explained in an interview. A model can later reword the messages, but the code decides which ones apply.

**Trade-off:** The thresholds are my first guesses and will need tuning with real use. The messages are plain, not personal.

## 046 - Check-ins use the same pure-rows pattern as plans

**Context:** Check-ins need storing. Database code is hard to test and easy to get subtly wrong.

**Decision:** A pure layer converts a check-in to plain rows (text, ints, None) and back, re-validating on load and raising a clear error for damaged data. The database layer will only copy rows in and out. Rows load in key order, so results do not depend on database ordering.

**Why:** The risky logic is tested without a database, including 500 random round-trips, and the same pattern already caught a real ordering bug in plan storage.

**Trade-off:** One more layer of small classes. It is worth it because the database code stays too simple to hide bugs.

## 047 - A check-in belongs to one stored plan and goes away with it

**Context:** A check-in only makes sense against the plan it describes. If the plan is replaced or deleted, the old check-in would describe tasks that no longer exist.

**Decision:** There is at most one check-in per stored plan (a unique constraint). Saving checks every reported task against the plan's placed tasks before anything is written, and replaces an earlier check-in for that day. Deleting or replacing a plan deletes its check-in in the same code path, and the database cascades as a second line of defence. Account export and delete cover check-ins, and the guard test lists them.

**Why:** The data can never disagree with itself, and a failed save leaves the old check-in untouched.

**Trade-off:** Re-planning a day discards that day's check-in. That is intended: if the plan changed, the old report is no longer about it.

## 048 - Check-in API: strict input, 422 for bad content, 404 for missing or foreign

**Context:** A check-in is typed by a person, often tired. The API must reject nonsense without ever storing half of it, and must not reveal whether another user has a plan or check-in.

**Decision:** Input is strict: whole numbers only (a string or a float for minutes is rejected), unknown fields are rejected, and lists and notes have size limits. Rules the field checks cannot see (a skipped task needs a reason, a task reported twice, a task that was not in the plan) come back as 422 from the same domain checks the database layer uses. A missing plan, a missing check-in and another user's data are all 404. The weekly review needs an explicit `end` date and covers the seven days ending on it, so the server never has to guess the user's time zone.

**Why:** One set of rules in code means the API, the storage layer and the tests cannot disagree. Rejecting before writing keeps the stored data clean.

**Trade-off:** A client has to send the date. That is more work for the client, but it avoids wrong-day bugs near midnight.

## 049 - The check-in logic gets its own eval, checked against deliberate breakage

**Context:** The weekly suggestions and the adherence numbers are rules in code. Unit tests cover single cases, but a rule can drift in ways no single test notices.

**Decision:** A fixed eval runs golden days and weeks with known answers, eleven attacks on stored rows that must be rejected, and a seeded random sweep (2000 days, 500 weeks) that checks invariants: adherence stays in 0..100, counted never exceeds planned, reported and unreported tasks partition the plan, storage round trips are exact, and each suggestion appears exactly when its rule says. It is part of the check script and CI. Tests also break a rule on purpose and require the eval to fail.

**Why:** A passing eval only means something if it can fail. Breaking rounding, a threshold, the keep-going rule and row validation each turned the eval red, which shows the gate works.

**Trade-off:** The eval encodes today's thresholds, so changing one means updating a golden case on purpose. Known gaps (no trend over weeks, self-reported reasons, untuned thresholds, no time-of-day link) are listed in the output and are not part of the gate.

## 050 - Experiment ratings are suggested from check-in data, never applied automatically

**Context:** A user rates a method they tried, and that rating steers which methods are suggested later. A rating from memory is noisy, but a rating the system sets on its own would take the choice away from the user.

**Decision:** An endpoint compares plan completion in the days of the experiment with the 14 days before it and returns a suggested rating (1 to 5) with a plain explanation. It needs at least 3 usable days on each side and otherwise returns no rating and says why. Cut-offs are 10 and 20 percentage points. The user still ends and rates the experiment through the existing endpoint. A running experiment needs an explicit `through` date, so the server never guesses the day.

**Why:** It keeps the rule "the system proposes, code verifies, the user decides", and the numbers can be checked and explained. It also stops a single good day from rating a method.

**Trade-off:** It cannot tell a helpful method from a good week for other reasons, so every message says the suggestion is not proof. Days come from the experiment's stored timestamp, so near midnight a day can be off by one for users far from UTC. That is a known gap.

## 051 - A persona eval scores the whole product on made-up users, with a scripted model

**Context:** The earlier evals each test one part: grounding, safety, retrieval, roadblocks, the pipeline, planning and check-ins. A real user goes through all of them in a row, and a part can pass alone and still fail in the chain.

**Decision:** 34 made-up users (`app/evals/personas_cases.py`) each carry words, optional activity data, a scripted model answer and a planning day. The runner sends them through detection and method suggestion, then plans their day and validates it with the independent validator, then runs five scripted check-in days and compares each adherence percent with a separate whole-number calculation. Five metrics are reported: detection, grounding, safety, plan constraints and check-ins. The gate is that every persona passes, and CI runs it.

**Why:** It is the one number that says the pieces work together, and it runs free and offline because the model is scripted. It reuses `run_case` instead of copying it, so the pipeline eval and the persona eval cannot drift apart. Tests break a label, the validator and the adherence figure on purpose and check that each turns the eval red.

**Trade-off:** The model is scripted, so this checks what the code does with a model answer, not how good a real model's answers are. The personas and their expected labels are written by hand, so they encode my own guesses about users, and five day shapes are reused across all of them. A real-model run on a small set of personas is a later, separate step.

## 052 - One generated eval report, and CI fails if it is stale

**Context:** Eight evals each print their own summary. A reader, or an interviewer, has no single place to see what is checked, what the numbers are and what is not proven.

**Decision:** `python -m app.evals.report` runs every eval's `main()`, captures what it prints and writes `docs/eval-report.md`: a table of all evals with PASS or FAIL, each eval's own output, and a section on what the evals do not prove. The report holds no dates or timings, so it only changes when a result changes. `--check` fails if the committed file differs from a fresh run or if any eval fails, and it runs in `scripts/check.sh` and CI.

**Why:** The numbers quoted in the README come from the code, not from memory, and they cannot go stale without CI saying so. Capturing each eval's printed summary means a new line in an eval shows up in the report with no change to the report script.

**Trade-off:** Changing any eval output means regenerating the report, which is one command but a small extra step. The report is only as precise as each eval's printed summary, and it says plainly that the model is scripted and the labels are hand-written.
