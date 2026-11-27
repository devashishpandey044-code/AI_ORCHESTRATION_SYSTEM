#!/usr/bin/env bash
# One-time setup per clone or Codespace: turns on the safety hooks and safer git defaults.
# Usage: bash scripts/setup-git.sh
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
chmod +x .githooks/* scripts/*.sh
git config core.hooksPath .githooks
git config pull.ff only
git config fetch.prune true
git config push.autoSetupRemote true
echo "Git safety is on: commits and pushes to main are blocked, pulls never create merge commits."
