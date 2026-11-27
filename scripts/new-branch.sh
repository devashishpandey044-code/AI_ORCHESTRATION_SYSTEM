#!/usr/bin/env bash
# Start a new branch from the latest GitHub main (never from a stale local copy).
# Usage: bash scripts/new-branch.sh feature/my-change
set -euo pipefail
name="${1:?Usage: bash scripts/new-branch.sh <branch-name>}"
cd "$(git rev-parse --show-toplevel)"

if [ "$name" = "main" ]; then
  echo "STOPPED: choose a branch name other than main."
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "STOPPED: you have uncommitted files. Commit them to your current branch,"
  echo "or save them with: git stash push -u -m my-work"
  exit 1
fi
if git show-ref --verify --quiet "refs/heads/$name"; then
  echo "STOPPED: a branch named $name already exists."
  exit 1
fi

git fetch origin --prune
git switch -c "$name" --no-track origin/main
echo "You are on $name, started from GitHub main at $(git rev-parse --short HEAD)."
