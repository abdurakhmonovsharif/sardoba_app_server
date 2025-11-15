# Sardoba Cashback App Backend

FastAPI backend for the Sardoba Cashback mobile application. Provides OTP authentication, staff management, cashback tracking, news management, catalog, notifications, caching, and administrative logging.

## Features
- Client OTP login with rate limiting
- Staff login with JWT access & refresh tokens
- Role-based authorization (manager, waiter)
- Cashback issuance and reporting
- News, catalog, and notifications management with cache invalidation
- Redis caching with in-memory fallback
- Structured logging and admin auth log viewer
- PostgreSQL with Alembic migrations
- Redis/DB/App docker-compose stack

## Getting Started
1. Create an environment file:
   ```bash
   cp .env.example .env
   ```
2. Start services:
   ```bash
   docker-compose up --build
   ```
3. Apply migrations:
   ```bash
   docker exec -it <app-container> alembic upgrade head
   ```
4. The API will be available at `http://localhost:8000/api/v1`.

## Local Development
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Running Tests
```bash
pytest
```

## Migrations
Generate a new migration:
```bash
alembic revision --autogenerate -m "message"
```
Apply migrations:
```bash
alembic upgrade head
```

## Configuration Notes
- OTP codes are random by default; set `OTP_STATIC_CODE` in your `.env` only if you need a fixed value for debugging.
- Use `OTP_RATE_LIMIT_BYPASS_PHONES` (comma separated) to exempt numbers such as `+99893143443` from OTP request throttling.

## Folder Structure
```
app/
  core/           # Config, database, security, caching
  models/         # SQLAlchemy models
  schemas/        # Pydantic schemas
  services/       # Business logic
  routers/        # API endpoints
main.py           # App factory
alembic/          # Migration scripts
```
