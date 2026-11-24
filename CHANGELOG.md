# Changelog

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
