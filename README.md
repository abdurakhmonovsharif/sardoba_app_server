# Sardoba Cashback App Backend

FastAPI backend for the Sardoba Cashback mobile application. Includes OTP-based client authentication, staff authentication, cashback tracking, catalog/news CRUD, notifications (REST + WebSocket), and IIKO integration.

## Quick Start (Docker)

1. Create `.env`:
   ```bash
   cp .env.example .env
   ```
2. Update `.env` (at minimum `DATABASE_URL`, JWT keys, IIKO keys, Eskiz keys).
3. Run:
   ```bash
   docker-compose up --build
   ```

API base: `http://localhost:8000/api/v1`  
Swagger UI: `http://localhost:8000/docs`  
OpenAPI JSON: `http://localhost:8000/openapi.json`

Note: `docker-compose.yml` runs only **app + redis**. PostgreSQL is **external** — `DATABASE_URL` must point to a reachable Postgres instance.

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Run on LAN:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Configuration (.env)

The config is defined in `app/core/config.py`.

**Required**
- `DATABASE_URL` (PostgreSQL connection string)
- `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`
- `IIKO_API_LOGIN`, `IIKO_ORGANIZATION_ID` (and optional `IIKO_API_BASE_URL`)
- `ESKIZ_LOGIN`, `ESKIZ_PASSWORD` (even if `SMS_DRY_RUN=true`, dummy values are still required)

**Common / Optional**
- `ENVIRONMENT` (`development` / `production`)
- `REDIS_URL` (if not set or Redis is unavailable, in-memory cache is used)
- `CORS_ORIGINS` (comma-separated or `*`)
- `SMS_DRY_RUN=true` to avoid sending real SMS in local/dev
- OTP settings: `OTP_STATIC_CODE`, `OTP_LENGTH`, `OTP_EXPIRATION_MINUTES`, `OTP_RATE_LIMIT_PER_HOUR`, `OTP_RATE_LIMIT_BYPASS_PHONES`
- Demo OTP settings: `DEMO_PHONE`, `OTP_DEMO_CODE` (see “Demo / test login” below)
- MyResto menu config: `MENU_API_URL`, `MENU_GIJDUVON_API_URL`, `STOP_LIST_API_URL`, `STOP_LIST_GIJDUVON_API_URL`, `STORE_IDS`, `MENU_CACHE_TTL`, `STOPLIST_CACHE_TTL`, `MENU_RESPONSE_CACHE_TTL`, `MENU_HTTP_TIMEOUT`

Errors are localized via `localize_message(...)` and may return as:
```json
{"ru": "...", "uz": "..."}
```

## Database Initialization (`init.sql`)

On startup `app/core/database_init.py` executes `init.sql` against `DATABASE_URL` (idempotent).

What it does:
- Creates required Postgres enum types
- Creates tables + indexes (if missing)
- Adds missing columns using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`

Recent schema additions:
- `users.surname`, `users.middle_name`, `users.pending_iiko_profile_update`
- `cashback_transactions.iiko_uoc_id`

## Authentication

### Client OTP flow
- `POST /api/v1/auth/client/request-otp` → sends OTP, returns `204`
- `POST /api/v1/auth/client/verify-otp` → verifies OTP, returns tokens
- `GET /api/v1/auth/me` → returns profile + cashback summary
- `POST /api/v1/auth/refresh` → refresh access token

### Staff flow
- `POST /api/v1/auth/staff/login` → returns staff profile + tokens (waiter also gets `clients`)
- `POST /api/v1/auth/staff/change-password`

### Demo / test login (no real OTP)

For development testing:
- `phone`: `+998911111111`
- `code`: `1111`

Request:
```json
POST /api/v1/auth/client/verify-otp
{"phone":"+998911111111","code":"1111","purpose":"login"}
```

This returns valid JWT tokens without creating an OTP row. Using that access token on `GET /api/v1/auth/me` returns a mock user profile (no DB/IIKO calls).

Production safety:
- If `ENVIRONMENT=production` and `DEMO_PHONE` is not set, the fallback demo phone is disabled.

## Notifications WebSocket

WebSocket: `ws://127.0.0.1:8000/api/v1/notifications/ws`

- Authenticate with header: `Authorization: Bearer <access_token>`
- Server replays unsent notifications stored in `user_notifications` and then streams new ones.

Token registration endpoint:
- `POST /api/v1/notifications/register-token` (for push token + language)

## Account deletion & re-registration

On delete the backend:
1. Generates a unique pseudo-number in the form `+999XXXXXXXXX`.
2. Marks the user as deleted and overwrites `phone` with the pseudo-number.
3. Writes the released real phone to `deleted_phones`.
4. Calls IIKO with `isDeleted=true` for that customer.

Deletion endpoints:
- `DELETE /api/v1/users/me` → `204 No Content`
- `DELETE /api/v1/user/delete` → `200 OK` + `{"success": true}`

## API Overview (Routes)

Base prefix is `API_V1_PREFIX` (default: `/api/v1`).

- `/health`
- `/auth/*` (client OTP + staff auth, refresh, me)
- `/users/*` (staff list/detail, client profile update/delete)
- `/cashback/*`
- `/files/*`
- `/news/*`
- `/catalog/*`
- `/notifications/*` (+ `/notifications/ws`)
- `/stats/*`
- `/dashboard/*`
- `/admin/*`
- `/iiko/*` (webhook + check-user)
- `/waiters/*`
- `/user/delete`

## Tests

```bash
pytest
```

If you see `Client.__init__() got an unexpected keyword argument 'app'`, your `httpx`/`starlette` versions are incompatible (Starlette `0.36.x` requires `httpx<0.28` for `TestClient`).

## Folder Structure

```
app/
  core/           # Config, DB init, security, caching, middleware
  models/         # SQLAlchemy models
  schemas/        # Pydantic schemas
  services/       # Business logic
  routers/        # API endpoints
alembic/          # Migration scripts (optional)
init.sql          # Idempotent schema init
```
