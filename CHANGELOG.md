# Changelog

## v0.5.0 - Check-ins and the weekly review

- Added check-ins: per planned task, done, partial or skipped, with minutes, a reason for a miss, energy and a note. Everything is validated, and bad combinations are rejected.
- Added a plan-versus-actual comparison: adherence in whole percent, overruns tracked separately, unreported tasks listed.
- Added a roadblock pattern finder: a reason counts only after repeating on several days, ranked by minutes lost.
- Added a weekly review with rule-based suggestions (plan less, longer estimates, protect energy, add buffer, smaller starts, keep going). No model call.
- Added storage (checkins, checkin_outcomes) with a migration. Deleting or replacing a plan removes its check-in. Account export and delete cover check-ins.
- Added API: PUT, GET and DELETE /checkins/{date}, GET /reviews/weekly, and GET /methods/experiments/{id}/suggested-rating.
- Added experiment rating suggestions from plan completion during versus before an experiment. The user still decides.
- Added a check-in eval (golden cases, tampered rows, a seeded sweep) to check.sh and CI, tested against deliberate breakage.
- Removed duplicate router registrations in app/main.py.

## v0.4.0 - Daily plan scheduler

- Added whole-minute interval maths and typed plan models (fixed events, sleep, tasks, breaks).
- Added a deterministic scheduler: priority order, earliest fit, focus tasks split into pieces with breaks, all-or-nothing per task, reasons for anything unplaced.
- Added an independent plan validator (10 violation codes) that re-checks any plan.
- Added a minimum-viable-day fallback for low-energy or overloaded days.
- Added a planning eval with golden, tampered and 1000-day random cases, wired into check.sh and CI.
- Added plan storage (plans, plan_tasks, plan_blocks) with a migration, re-validated when loaded.
- Added API: POST, GET and DELETE /plans/{plan_date}, scoped per user.
- Account export and delete now cover plans, with a guard test that fails if a new user table is not handled.

## v0.3.0 - Week 3
- Methodology library: roadblock taxonomy, strictly validated method schema, 11 curated methods
  with honest evidence levels and review dates, coverage report.
- Retrieval: local deterministic embedder, in-memory and pgvector stores, idempotent indexer,
  filter-then-rank selection, retrieval eval, migration guard tests.
- Roadblock detection: activity rules with documented thresholds and model proposals that must
  quote the user's own words; fixed care note for energy-related results.
- Method selection: at most two suggestions, history-aware, with experiment tracking.
- Pipeline eval: golden cases and an invariant sweep over all roadblock combinations.
- Engineering: git safety scripts and hooks, `scripts/check.sh`, CI with a real Postgres.

## v0.2.0 - Week 2
- LLM layer: provider interface, fake and Anthropic providers, validated structured output with
  one retry, call log with metadata only.
- Life Model: immutable versions with provenance (stated, belief, inferred), edit, history and
  restore, race protection through a unique constraint.
- Onboarding: propose, verify against the user's own words, then confirm; per-user daily limit.
- Safety: crisis check before any model call, fixed support response, anonymous event log.
- Evals: grounding eval and safety eval, both run in CI.
- Account export and deletion now cover the new tables.

## v0.1.0 - Week 1
- Auth, goals hierarchy and tree, schedule constraints, account export and deletion,
  migrations, tests, CI.
