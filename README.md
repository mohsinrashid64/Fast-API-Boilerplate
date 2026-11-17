# FastAPI Async Boilerplate

An async FastAPI starter with JWT auth, OTP verification (email / SMS), password reset,
a sample `Product` resource, Alembic migrations, and a **Django-style admin panel**.

**Stack:** FastAPI · SQLAlchemy 2 (async) · Pydantic v2 · Alembic · SQLAdmin · SQLite (default) or PostgreSQL

## Quick start

Requires **Python 3.12+**.

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt      # or requirements-dev.txt to also get the test tools

uvicorn app.main:app --reload        # or: python scripts/run_dev.py
```

Open http://localhost:8000. A fresh install sends you to the **setup wizard** (`/setup`):
pick **local SQLite** (one click) or paste a **PostgreSQL** connection string, then create your admin
account. The wizard runs the migrations and saves everything to `.env`. `SECRET_KEY` and
`ENCRYPTION_KEY` are generated for you on first start.

Prefer the terminal? Copy `.env.example` to `.env`, fill in `DATABASE_URL`, and run
`alembic upgrade head` and then `python scripts/create_superuser.py`.

| URL | What |
| --- | --- |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/redoc | ReDoc |
| http://localhost:8000/admin | Admin panel (superusers only) |

In development, if SMTP / AWS credentials are not set, emails and SMS (including OTP codes)
are printed to the server log instead of being sent.

## Admin panel

Built with [SQLAdmin](https://aminalaee.github.io/sqladmin/). Code lives in [`app/admin/`](app/admin/).

- **Login:** any user with `is_superuser = true` and `is_active = true` (username or email + password).
  Access is re-checked on every request, so un-ticking *Superuser* or *Active* locks a user out immediately.
- **Dashboard:** totals plus the newest users and products.
- **Users:** search, filter (verified / active / superuser), create and edit, and a *Password* field to set or reset
  a user's login password. Admins can't demote, deactivate or delete themselves.
- **Products:** full CRUD with owner lookup, search, sort, filter by owner, and CSV export.
- **Login methods, OTPs, reset tokens:** view and delete only. Secrets are masked or hidden.

`python scripts/create_superuser.py` works like Django's `createsuperuser`. It prompts for the details,
or you can pass `--username/--email/--password --no-input`. Running it for an existing user promotes that user.

**Adding a model to the admin:** add a `ModelView` in [`app/admin/views.py`](app/admin/views.py) and append it to `ALL_VIEWS`.

## Database setup & switching

| Where | What it does |
| --- | --- |
| `/setup` | First-run wizard. Only exists while no database is configured, and only answers `localhost` (`SETUP_ALLOW_REMOTE=true` to change). Returns 404 afterwards. |
| Admin, **Database** page | Shows the connection (password masked), size, tables and migration status. Has a **Run pending migrations** button and a **Switch database** flow. |

**Switching databases** from the admin:
1. tests the connection;
2. creates the tables and runs all migrations in the new database;
3. copies your admin account so you can still log in;
4. writes `DATABASE_URL` to `.env`.

The running server keeps using the old database until you **restart it**, and every admin page shows a banner until then. You can also cancel the switch. **Data is not copied.**

**Supported URLs:** SQLite (`sqlite:///./file.db`) and PostgreSQL (`postgresql://user:pass@host:5432/db`).
`postgres://…` and libpq options like `?sslmode=require` (Heroku, Neon, Supabase) are converted to the
async `asyncpg` driver automatically.

**Production:** the wizard and switching are off when `ENVIRONMENT=production` unless you set
`ALLOW_SETUP_WIZARD` / `ALLOW_DB_SWITCH`. Missing `DATABASE_URL` / `SECRET_KEY` / `ENCRYPTION_KEY` then
stop the app at startup. A real `DATABASE_URL` environment variable always wins over `.env`, and the admin
then tells you to change it in your server's environment instead.

## Table builder (Schema page, development only)

Admin, then **Schema**, then **New table**. Design a table:
- columns: name, type, size, required/unique/index, default;
- relations: a foreign key to any existing table, with ON DELETE;
- options:
  - timestamps;
  - login-protected API;
  - records owned by the logged-in user;
  - tests;
  - apply the migration.

Click **Preview code** to see every file, then **Create table**. It writes:

| File | What |
| --- | --- |
| `app/models/<name>.py` | SQLAlchemy model |
| `app/schemas/<name>.py` | Pydantic `Create` / `Update` / `Out` schemas |
| `app/crud/<name>_crud.py` | `CRUDBase` instance |
| `app/routes/<name>.py` | `GET/POST /<table>/`, `GET/PUT/PATCH/DELETE /<table>/{id}` |
| `alembic/versions/NNNN_create_<table>.py` | migration (applied immediately unless you untick it) |
| `tests/test_<name>_api.py` | API tests for the new endpoints |

Nothing else needs registering:
- every module in `app/models/` and `app/routes/` is loaded automatically;
- every model without a hand-written admin view gets an automatic admin page.

With `uvicorn --reload` the server restarts by itself and the diagram opens on the new table.
Without it, restart the server.

The files are ordinary code you own. To change a table later, edit the model and run
`alembic revision --autogenerate -m "..."`. The builder never overwrites files and is disabled when
`ENVIRONMENT=production`.

## Database migrations (Alembic)

```bash
alembic revision --autogenerate -m "describe change"   # after editing models
alembic upgrade head                                     # apply
alembic downgrade -1                                     # roll back one step
```

**Upgrading an existing `power.db`** created by an older version of this project (via `create_all`, before Alembic):

```bash
alembic stamp 0001 && alembic upgrade head
```

## Configuration

All settings are read from environment variables or `.env` through [`app/core/config.py`](app/core/config.py).
See [`.env.example`](.env.example) for the full list. `SECRET_KEY` and `ENCRYPTION_KEY` are required.
Keep `ENCRYPTION_KEY` stable: it encrypts the `user_id` returned by signup and login.

## Auth flow

1. `POST /auth/signup` creates the user and sends an OTP. It returns an encrypted `user_id`.
2. `POST /otp/verify` with `{user_id, otp_code}` marks the account verified.
   `POST /otp/generate` re-sends a code.
3. `POST /auth/login` returns `{access_token}`. Send it as `Authorization: Bearer <token>`.
   If the account isn't verified yet, login sends a new OTP instead.
4. `POST /auth/forgot-password`, then `POST /auth/reset-password`.

Protected routes declare `Depends(get_current_user)`, or `get_current_superuser` for admin-only routes.
Both are in [`app/core/deps.py`](app/core/deps.py).

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Production

```bash
ENVIRONMENT=production python scripts/run_prod.py   # gunicorn + uvicorn workers; reads HOST/PORT/WORKERS
```

In production, error details are hidden, the admin session cookie is HTTPS-only, and missing SMTP/AWS
credentials raise errors instead of being logged.

## Project layout

```
app/
  admin/        SQLAdmin views, auth backend, dashboard
  core/         settings, error handlers, auth dependencies
  crud/         generic async CRUD (user-scoped)
  database/     engine, session, Base
  models/       SQLAlchemy models
  routes/       API routers
  schemas/      Pydantic models
  services/     business logic (auth, OTP, users)
  utils/        jwt, hashing, crypto, email, sms, ...
alembic/        migrations
scripts/        run_dev, run_prod, create_superuser
tests/          pytest suite
```
