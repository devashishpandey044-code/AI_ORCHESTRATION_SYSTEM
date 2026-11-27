#!/usr/bin/env bash
# Prints a login token for the dev user. Usage: TOKEN=$(bash scripts/token.sh)
resp=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"me@example.com","password":"my-long-password-1"}')
python - "$resp" <<'PY'
import json
import sys

try:
    print(json.loads(sys.argv[1])["access_token"])
except Exception:
    shown = sys.argv[1] or "(nothing - is the server running?)"
    sys.stderr.write("Login failed. Server said: " + shown + "\n")
    sys.exit(1)
PY
