#!/bin/bash
set -e

echo "⏳ Waiting for external PostgreSQL to be ready..."
# Adjust these values if necessary — they come from .env

echo "✅ Starting FastAPI app..."
# Database schema initialization happens automatically on app startup via init_database_schema()
# Alembic migrations are no longer needed as we use idempotent SQL initialization
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
