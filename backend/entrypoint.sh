#!/usr/bin/env sh
set -e

echo "==> Running Alembic migrations..."
alembic upgrade head

echo "==> Seeding default settings and prompts..."
python -m app.bootstrap.seed

echo "==> Starting uvicorn..."
if [ "${UVICORN_RELOAD:-0}" = "1" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
