# CLAUDE.md

Guidance for Claude (and humans) working in this repo, plus a running history of changes.
**Keep it current:** after any meaningful change, add a dated entry to [History](#history), and update the
other sections if conventions or commands changed.

> **Building features or a new backend on this boilerplate?** Follow [AI_GUIDE.md](AI_GUIDE.md): the
> playbook for adding resources, where code goes, FastAPI/SQLAlchemy performance rules, the security
> checklist and the definition of done.

## Project
An async FastAPI boilerplate. The pieces:
- JWT auth with OTP verification (email/SMS) and password reset.
- A sample `Product` resource.
- Alembic migrations.
- A Django-style admin panel (SQLAdmin) with:
  - a dashboard;
  - an ER diagram ("Schema") with a **table builder** that generates code;
  - a "Database" page;
  - a first-run **setup wizard** (`/setup`).

**Stack:** Python 3.12+ (developed on 3.14), FastAPI, SQLAlchemy 2.1 async, Pydantic v2, Alembic, SQLAdmin 0.32, SQLite (`aiosqlite`) or PostgreSQL (`asyncpg`).

## Commands
```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload          # dev server. --reload matters for the table builder
pytest -q                              # full suite (about 25s; includes an isolated end-to-end codegen run)
alembic upgrade head                   # apply migrations
alembic revision --autogenerate -m ""  # after changing models
alembic check                          # models and migrations must not drift (also a test)
python scripts/create_superuser.py     # Django-style createsuperuser
```

## Layout
```
app/
  admin/      SQLAdmin:
                __init__.py   AppAdmin: dashboard index + paged ajax lookup; setup_admin()
                views.py      BaseAdminView, hand-written views, auto_view(), all_views()
                relations.py  automatic searchable relationship dropdowns
                auth.py       superuser session login
                erd.py        Schema page + table builder endpoint
                schema.py     introspection for the ERD
                database.py   Database page
                templates/    layout/base/login overrides, admin_theme.css, erd.html, dashboard.html, database.html
  codegen/    table builder: spec.py (validation), generator.py, templates/*.py.j2
  core/       config (settings), deps (get_current_user / get_current_superuser), env_file (.env writer),
              db_admin (URL normalising, connection test, migrations), error_handlers
  crud/       CRUDBase (user-scoped, async)
  database/   lazy engine: init_engine/get_engine, AsyncSessionLocal (unbound until configured), Base
  models/     auto-imported: every module here is registered (no edits to __init__ needed)
  routes/     auto-included: core routers first, then every module defining `router`
  schemas/  services/  utils/
  setup/      /setup first-run wizard + guard middleware
alembic/      env.py honours Config.attributes["database_url"] and ["configure_logger"]
scripts/      run_dev, run_prod (gunicorn + uvicorn-worker), create_superuser
tests/        pytest; conftest isolates ENV_FILE/DB in a temp dir
```

## Conventions
- **Config:** read config only via `app.core.config.settings` (never `os.getenv`). Real environment variables beat `.env`.
- **`.env` location and writing:** `.env` lives at the project root (or wherever `ENV_FILE` points). Write to it only through `app/core/env_file.update_env`.
- **Engine access:** never import a module-level `engine`. Use `get_engine()` / `AsyncSessionLocal` (which can be unbound in setup mode).
- **Auth:** done with dependencies (`Depends(get_current_user)`), not middleware.
- **Datetimes:** naive UTC everywhere (`app/utils/time.utcnow()`), because SQLite has no timezone support.
- **Model labels:** `Base.__str__` gives every model a readable label (name/title/username/email…). Override it per model if needed.
- **New tables need no registration:** models/routes are auto-discovered, and models without a hand-written admin view get `auto_view()`.
- **Generated code** (table builder) is ordinary code the user owns. The builder never overwrites files and is disabled when `ENVIRONMENT=production`.
- **Tests:**
  - Never touch the real `.env` or `power.db`. Use temp paths, and `ENV_FILE` for anything that writes `.env`.
  - Codegen tests use the name `sample_gadgets`, which won't clash with the user's tables.
  - Don't assert the exact set of tables or migrations: the user generates more.
- **Browser checks:** done on a scratch copy of the project with headless Firefox and Selenium (in a scratch venv), never in the repo.

## Gotchas (learned the hard way)
- **SQLAdmin:**
  - It has no form converter for SQLAlchemy 2.1 `Float`. `BaseAdminView` auto-adds `FloatField` overrides.
  - It lists only the primary key unless `column_list` is set. `auto_view()` sets it.
  - With several `@expose` routes on one `BaseView`, the menu link follows the **last** identity. Use one route with GET+POST and an `action` field.
  - Its select2 lookup requires 1 typed character and 400s on an empty term. `AppAdmin.ajax_lookup` and the JS in `templates/sqladmin/base.html` override this.
- **FastAPI 0.163** nests included routers (`_IncludedRouter.original_router`), so `router.routes` has no paths. See `_route_paths()` in `app/codegen/spec.py`.
- **Alembic:** its `env.py` calls `asyncio.run`, so from async code run it via `asyncio.to_thread` (see `db_admin.migrate_to_head`).
- **Jinja:**
  - Blocks can't see variables set in a parent block unless declared `scoped` (see `layout.html`).
  - `tojson` sorts keys.
- **Tabler CSS:** `.row-deck` makes columns flex rows. Full-width custom content needs `display:block` (dashboard) or `width:100%` (ERD).
- **SQLite** ignores foreign keys unless `PRAGMA foreign_keys=ON`. `init_engine` enables it.
- **`CRUDBase.create`** uses `model_dump(exclude_unset=True)` so column defaults (e.g. `func.now()`) aren't overwritten with NULL.

## Known open items
- **Leaked password:** a Gmail app password was committed in an early version of `app/utils/email_util.py` and is still in git history. The user must revoke it. Rewriting history is their call.
- **Skipped generated tests:** the tests generated for `categories` / `reviews` are skipped because they require a `products` row. Add one in each test to enable them.
- **Table builder scope:** create only. Changing or dropping generated tables is done in code plus `alembic revision --autogenerate`.
- **Switching databases** from the admin needs a server restart and doesn't copy data, by design.
- **Performance debt** (details in AI_GUIDE.md §8):
  - bcrypt `Hash.hash`/`verify` run on the event loop (should use `asyncio.to_thread`);
  - the engine pool isn't tuned for PostgreSQL production.

## History
All dates are 2026-11-17 unless noted. Nothing has been committed by Claude; the user commits.

1. **Analysis.** Found the following problems:
   - a hardcoded Gmail password;
   - a product ownership bypass on PUT/PATCH;
   - a public `/users` endpoint;
   - a Fernet key regenerated on every boot;
   - broken async forgot/reset-password, OTP-generate and SMS endpoints;
   - UTF-16, bloated `requirements.txt`;
   - no migrations and no tests.
2. **Admin panel (SQLAdmin) and full cleanup:**
   - superuser session login;
   - views for all models, with a "set password" field on users and self-lockout guards;
   - dashboard;
   - `create_superuser` script;
   - Alembic (`0001` baseline, `0002` `is_active`/`is_superuser`);
   - unified settings;
   - lifespan instead of `on_event`;
   - dependency-only auth (`AuthMiddleware` removed);
   - PyJWT and bcrypt (instead of python-jose and passlib);
   - a fixed and slimmed requirements file;
   - pytest suite.
3. **Admin redesign:** custom layout (sidebar, breadcrumbs, page headers), theme CSS, login page, dashboard KPI cards, readable labels and value formatters.
4. **Sidebar:** flat "Tables" section; "Login Methods" renamed to "User Auth".
5. **Schema page:** an interactive ER diagram generated from the models. Drag, pan, zoom, search, hover highlights, crow's-foot notation, details drawer, and layout saved per browser.
6. **Setup wizard and Database page:**
   - `/setup` on first run: SQLite or PostgreSQL, test connection, run migrations, create the superuser, write `.env`;
   - admin Database page: status, migration list, run migrations, and a guarded "switch database" flow (copies the admin account; restart required) with a restart banner;
   - lazy engine;
   - keys auto-generated outside production.

   Verified against real PostgreSQL 16 in Podman.
7. **Relationship dropdowns:** automatic for every relationship, listing records on open, searchable, paged by 20. Sensitive columns are never searchable. Added `Base.__str__` labels.
8. **Table builder** (Schema → New table): generates model, schemas, CRUD, routes, migration and tests; applies the migration; waits for the server to reload, then focuses the new table. Supporting changes:
   - auto-discovery of models, routes and admin views;
   - SQLite FK pragma;
   - generic Float form fix.

   The user then generated `categories` (migration `0003`) and `reviews` (`0004`) with it.
9. **Table builder UI redesign:** full-size dialog, numbered section cards, column cards with labelled toggles, sentence-style relations, option switches, live preview panel (table card, endpoints, files), step indicator, file-list code review.

   Tests made resilient to user-generated tables.
10. **Added this `CLAUDE.md`.**
11. **Added `AI_GUIDE.md`:** a playbook for building new backends on the boilerplate. It covers:
    - bootstrapping and removing the sample product;
    - the resource recipe (table builder or by hand);
    - the code-placement table;
    - async/SQLAlchemy performance rules;
    - production settings, security, testing, and the definition of done.

    It also records the known performance debt.
