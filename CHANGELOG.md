# Changelog

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
