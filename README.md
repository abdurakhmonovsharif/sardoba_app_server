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
- WebSocket-first notifications with persisted backlog
- Account deletion frees the real phone by rotating it to a dedicated +999… pseudonumber and logging the release.

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
# run as with LAN IP
 uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
## Notifications WebSocket

The backend now relies solely on the websocket at `ws://127.0.0.1:8000/api/v1/notifications/ws` (replace with the actual host in production). Clients authenticate with `Authorization: Bearer <access_token>` and receive any pending notifications that were recorded while they were offline plus new cashback events the moment they arrive. Each message matches the shape stored in `user_notifications` (`title`, `description`, `payload`, `language`, etc.).

Call `/api/v1/notifications/register-token` with `deviceType=ios` and `deviceToken=null` if the client only listens via websocket; this also helps the server guess a preferred language for the user.

## Admin Notifications

Managers can push custom notifications to specific users via `POST /api/v1/notifications/send`. Provide `userIds`, `title`, `description`, and optional `notificationType`, `payload`, and `language`; the system stores each notification in `user_notifications` and attempts to deliver it over the websocket once the user is connected. Notifications are only delivered once, and undelivered ones are replayed whenever the client reconnects.

## Account deletion & re-registration

When a user deletes their account the backend:

1. Generates a unique pseudo-number in the form `+999XXXXXXX`.
2. Marks the user as deleted (`deleted = true`), updates `deleted_at`, and overwrites `phone` with the pseudo-number.
3. Logs the released real phone in `deleted_phones`.
4. Calls Iiko with `deleted=true` so their customer record is synced.

Call `DELETE /api/v1/user/delete` when the mobile user issues a permanent delete; it returns `{"success": true}`. Once deleted, the real phone is freed, and logging in is blocked because the `deleted` flag is in place.

To reuse the same phone, simply register again — the system will detect that the prior user was deleted (phone starts with `+999`) and create a brand-new client each time.

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
