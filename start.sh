#!/bin/bash
set -e

echo "⏳ Waiting for external PostgreSQL to be ready..."
# Adjust these values if necessary — they come from .env
until pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER"; do
  sleep 2
done

echo "🚀 Running Alembic migrations..."
alembic upgrade head

echo "✅ Starting FastAPI app..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
