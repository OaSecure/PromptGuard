#!/usr/bin/env sh
set -eu

MAX_ATTEMPTS="${PROMPTGUARD_DB_STARTUP_ATTEMPTS:-30}"
SLEEP_SECONDS="${PROMPTGUARD_DB_STARTUP_SLEEP_SECONDS:-2}"
attempt=1

until alembic current >/dev/null 2>&1; do
  if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
    echo "[startup] database is not ready for migrations"
    exit 1
  fi
  echo "[startup] waiting for database (${attempt}/${MAX_ATTEMPTS})"
  attempt=$((attempt + 1))
  sleep "$SLEEP_SECONDS"
done

echo "[startup] running alembic migrations"
alembic upgrade head

echo "[startup] running initial seed"
python -m app.db.seed

echo "[startup] starting api"
exec uvicorn app.main:app \
  --host "${PROMPTGUARD_API_HOST:-0.0.0.0}" \
  --port "${PROMPTGUARD_API_PORT:-8000}" \
  --reload
