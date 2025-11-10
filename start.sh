#!/bin/bash
set -e

echo "⏳ Waiting for external PostgreSQL to be ready..."
# Adjust these values if necessary — they come from .env

echo "🚀 Running Alembic migrations..."
alembic upgrade head

echo "✅ Starting FastAPI app..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
