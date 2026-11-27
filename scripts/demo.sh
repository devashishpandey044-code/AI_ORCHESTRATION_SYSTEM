#!/usr/bin/env bash
# Starts the database and the API, runs the 2-minute demo story, then stops the server.
# Usage: bash scripts/demo.sh          run the demo and stop
#        bash scripts/demo.sh --keep   run the demo and leave the server running
cd "$(dirname "$0")/.." || exit 1

docker compose up -d db >/dev/null 2>&1
for _ in $(seq 1 30); do
  docker compose exec -T db pg_isready -U lifeos >/dev/null 2>&1 && break
  sleep 1
done

alembic upgrade head >/tmp/alembic.log 2>&1 || {
  echo "Migration failed. See /tmp/alembic.log"
  exit 1
}

uvicorn app.main:app --port 8000 >/tmp/uvicorn.log 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT

ready=0
for _ in $(seq 1 30); do
  if [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health/ready)" = "200" ]; then
    ready=1
    break
  fi
  sleep 1
done
if [ "$ready" != 1 ]; then
  echo "The server did not become ready. See /tmp/uvicorn.log"
  exit 1
fi

python -m app.demo.run --base-url http://localhost:8000
code=$?

if [ "${1:-}" = "--keep" ]; then
  trap - EXIT
  echo "Server left running (pid $SERVER). Stop it with: kill $SERVER"
fi
exit $code
