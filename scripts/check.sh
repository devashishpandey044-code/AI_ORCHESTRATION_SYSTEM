#!/usr/bin/env bash
# Run every check that CI runs and print one summary line. Usage: bash scripts/check.sh
# Tip: run `unset TEST_POSTGRES_URL` first for the quick version without Postgres tests.
cd "$(git rev-parse --show-toplevel)" || exit 1
fail=0
run() {
  echo "== $*"
  "$@" || fail=1
}
run python -m pytest -q
run ruff check .
run python -m app.evals.grounding
run python -m app.evals.safety
run python -m app.evals.retrieval
run python -m app.evals.roadblocks
if [ "$fail" = "0" ]; then
  echo "ALL CHECKS PASSED"
else
  echo "SOMETHING FAILED (scroll up to the first red line)"
  exit 1
fi
