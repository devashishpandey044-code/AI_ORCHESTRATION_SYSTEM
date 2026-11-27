#!/usr/bin/env bash
# Make local main identical to GitHub main. Saves any local-only commits to a backup branch first.
# Usage: bash scripts/sync-main.sh
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

if [ -n "$(git status --porcelain)" ]; then
  echo "STOPPED: you have uncommitted files. Save them first:"
  echo "  commit them on your feature branch, or run: git stash push -u -m my-work"
  exit 1
fi

git fetch origin --prune
if ! git show-ref --verify --quiet refs/heads/main; then
  git branch main origin/main
fi
git checkout main

ahead=$(git rev-list --count origin/main..main)
if [ "$ahead" != "0" ]; then
  backup="backup-main-$(date +%Y%m%d-%H%M%S)"
  git branch "$backup" main
  echo "Saved $ahead local-only commit(s) on branch $backup (nothing is lost)."
fi

git reset --hard origin/main
echo "Local main now matches GitHub main at $(git rev-parse --short HEAD)."
