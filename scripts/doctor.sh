#!/usr/bin/env bash
# Shows exactly where your checkout stands, so a stale or wrong branch is obvious.
# Usage: bash scripts/doctor.sh
cd "$(git rev-parse --show-toplevel)" || exit 1
if ! git fetch origin --prune --quiet; then
  echo "Could not reach GitHub (git fetch failed). Check your connection."
  exit 1
fi

branch=$(git branch --show-current)
echo "Branch .............. ${branch:-detached}"

changes=$(git status --porcelain | wc -l | tr -d ' ')
if [ "$changes" = "0" ]; then
  echo "Uncommitted files ... none"
else
  echo "Uncommitted files ... $changes  (see them with: git status --short)"
fi

if git show-ref --verify --quiet refs/heads/main; then
  read -r ahead behind < <(git rev-list --left-right --count main...origin/main)
  if [ "$ahead" = "0" ] && [ "$behind" = "0" ]; then
    echo "Local main .......... in sync with GitHub"
  elif [ "$ahead" = "0" ]; then
    echo "Local main .......... BEHIND GitHub by $behind commit(s)  -> bash scripts/sync-main.sh"
  elif [ "$behind" = "0" ]; then
    echo "Local main .......... AHEAD by $ahead local-only commit(s)  -> bash scripts/sync-main.sh"
  else
    echo "Local main .......... DIVERGED ($ahead local-only, $behind missing)  -> bash scripts/sync-main.sh"
  fi
else
  echo "Local main .......... not used (fine: you branch from origin/main)"
fi

missing=$(git rev-list --count HEAD..origin/main)
if [ "$missing" = "0" ]; then
  echo "This branch ......... contains the latest GitHub main"
else
  echo "This branch ......... is MISSING $missing commit(s) from GitHub main"
  echo "                      (on a feature branch, bring them in with: git merge origin/main)"
fi
