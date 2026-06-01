#!/usr/bin/env sh
set -eu

echo "[startup] waiting for database"
python -m app.db.wait_for_db

echo "[startup] running alembic migrations"
alembic upgrade head

echo "[startup] running initial seed"
python -m app.db.seed

echo "[startup] starting api"
exec uvicorn app.main:app \
  --host "${PROMPTGUARD_API_HOST:-0.0.0.0}" \
  --port "${PROMPTGUARD_API_PORT:-8000}" \
  --reload
