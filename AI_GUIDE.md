# AI Guide: building a backend on this boilerplate

A playbook for an AI coding assistant (or a developer) starting a **new backend** from this repo.
It covers how to bootstrap the project, how to add features the way this codebase expects, and how to
write FastAPI code that stays fast. Project facts, commands and known library quirks are in
[CLAUDE.md](CLAUDE.md); read that first. This file doesn't repeat them.

**Golden rules**
1. **Follow the existing patterns.** Model → schema → CRUD/service → router → migration → test. Consistency beats cleverness.
2. **Never block the event loop.** Every route is `async def`; anything slow and synchronous goes through `await asyncio.to_thread(...)` or a worker queue.
3. **One `AsyncSession` per request** (`Depends(get_db)`), one commit per unit of work, no lazy loading.
4. **Every change ships with:** a migration (`alembic check` clean), tests (`pytest -q` green) and a `CLAUDE.md` history entry.

---

## 1. Starting a new backend

1. **Clone and install:**
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements-dev.txt
   uvicorn app.main:app --reload
   ```
2. **Configure.** Open `http://localhost:8000` to get the setup wizard: pick SQLite or PostgreSQL and create the superuser.
   - Headless alternative: set `DATABASE_URL` in `.env`, then run `alembic upgrade head` and `python scripts/create_superuser.py`.
3. **Rename** `APP_NAME` in `.env`. Set `CORS_ORIGINS` and `FRONTEND_URL` for your frontend.
4. **Decide on the sample/auth features.** Keep users, auth, OTP and password reset (most backends need them).
   - Remove `Product` only if it's unwanted. To remove it:
     1. delete `app/models/product.py`, `app/schemas/product.py`, `app/crud/product_crud.py` and `app/routes/product.py`;
     2. remove `"product"` from `CORE_MODULES` in `app/routes/__init__.py`;
     3. remove `Product` from the explicit imports in `app/models/__init__.py`, the `products` relationship in `app/models/user.py`, and `ProductAdmin` in `app/admin/views.py`;
     4. remove the product schema exports in `app/schemas/__init__.py`, the `product_crud` export in `app/crud/__init__.py`, and the product queries in the dashboard (`app/admin/__init__.py`);
     5. `alembic revision --autogenerate -m "drop products"`;
     6. delete or adjust `tests/test_products.py` and the product-related admin tests.
5. **Model the domain.** Sketch the tables and relations first; the admin **Schema** page shows them as you go.
6. **Build each resource** with the table builder or the hand-written recipe below.
7. **Add business logic** in services (section 3), not in routers.
8. **Before calling it done,** go through the [Definition of done](#7-definition-of-done).

---

## 2. Adding a resource (CRUD)

### Option A: the table builder (fastest, development only)
Admin → **Schema** → **New table**. It generates the model, schemas, CRUD, routes, a migration (applied immediately) and tests. Nothing needs registering: models, routes and admin views are auto-discovered.

Then **edit the generated files** like any other code (add validation, custom queries, business rules).
If you change the model afterwards: `alembic revision --autogenerate -m "..."`.

### Option B: by hand (for anything the builder can't express)
Mirror the layout of `app/*/product*.py`. File names use the singular snake_case of the model: `order_item.py` for `OrderItem`.

**Model:** `app/models/order.py` (auto-imported, no registration needed)
```python
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import relationship

from app.database.db_config import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String(40), nullable=False, unique=True)
    total = Column(Numeric(12, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending", index=True)  # index what you filter on
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)  # always index FKs
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user = relationship("User", lazy="raise")  # forces explicit loading; see section 4
```

**Schemas:** `app/schemas/order.py`. Keep separate `Create` / `Update` (all optional) / `Out` models.
```python
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OrderBase(BaseModel):
    reference: str = Field(..., max_length=40)
    total: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    status: str = Field("pending", max_length=20)


class OrderCreate(OrderBase):
    pass


class OrderUpdate(BaseModel):
    reference: str | None = Field(None, max_length=40)
    total: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    status: str | None = Field(None, max_length=20)


class OrderOut(OrderBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime | None = None
```

**CRUD:** `app/crud/order_crud.py`
```python
from app.crud.base import CRUDBase
from app.models.order import Order
from app.schemas.order import OrderCreate, OrderUpdate

order_crud = CRUDBase[Order, OrderCreate, OrderUpdate](Order)
```
`CRUDBase` gives `get`, `get_all`, `create`, `update` (partial) and `delete`. Passing `user_id=` scopes any of them to the owner: other users' rows behave as 404.

**Router:** `app/routes/order.py` (auto-included when it defines `router`)
```python
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.crud.order_crud import order_crud
from app.database import get_db
from app.models import User
from app.schemas.order import OrderCreate, OrderOut, OrderUpdate

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("/", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(data: OrderCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await order_crud.create(db, obj_in=data, user_id=user.id)


@router.get("/", response_model=list[OrderOut])
async def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),  # always cap page size
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await order_crud.get_all(db, skip=skip, limit=limit, user_id=user.id)


@router.patch("/{order_id}", response_model=OrderOut)
async def update_order(order_id: int, data: OrderUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    order = await order_crud.get(db, id=order_id, user_id=user.id)
    return await order_crud.update(db, db_obj=order, obj_in=data)
```

**Migration:**
```bash
alembic revision --autogenerate -m "create orders"
alembic upgrade head
alembic check   # must print "No new upgrade operations detected"
```
Always read the generated migration. Autogenerate misses some things (renames look like drop+add, server defaults, enum changes).

**Admin:** nothing to do; the model gets an automatic admin page. Write a `BaseAdminView` subclass in `app/admin/views.py` and add it to `ALL_VIEWS` only when you need custom columns, filters, formatters or form rules.

**Tests:** `tests/test_order_api.py`, using the shared fixtures:
```python
from tests.conftest import auth_headers


async def test_orders_are_private(client, make_user):
    alice, bob = await make_user("alice"), await make_user("bob")
    r = await client.post("/orders/", json={"reference": "A-1"}, headers=auth_headers(alice))
    assert r.status_code == 201
    order_id = r.json()["id"]
    assert (await client.get("/orders/", headers=auth_headers(bob))).json() == []
    assert (await client.patch(f"/orders/{order_id}", json={"status": "paid"}, headers=auth_headers(bob))).status_code == 404
```

---

## 3. Where code goes

| Concern | Place | Rule |
| --- | --- | --- |
| HTTP shape (paths, status codes, auth deps, pagination params) | `app/routes/` | Thin. No queries beyond calling CRUD or a service. |
| Validation and serialization | `app/schemas/` | Pydantic v2. Validators raise `ValueError` (becomes 422), never `HTTPException`. |
| Simple persistence | `app/crud/` | `CRUDBase` instances. |
| Business logic (several tables, external calls, rules) | `app/services/` | A class taking `AsyncSession`, like `AuthService`. Raises `HTTPException` for client errors. |
| Auth and permissions | `app/core/deps.py` | `get_current_user`, `get_current_superuser`. Add role dependencies here. |
| Config | `app/core/config.py` | New setting = a typed field on `Settings` plus a line in `.env.example`. |
| External integrations | `app/utils/` | Async clients only; config from `settings`; log-instead-of-send in development (see `email_util.py`). |
| Admin customisation | `app/admin/views.py` | Subclass `BaseAdminView`, add to `ALL_VIEWS`. |

**Service pattern:**
```python
class CheckoutService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def place_order(self, user: User, items: list[ItemIn]) -> Order:
        products = await self._load_products([i.product_id for i in items])  # one query, not one per item
        order = Order(user_id=user.id, reference=new_reference(), total=sum_totals(products, items))
        self.db.add(order)
        await self.db.commit()  # one transaction for the whole operation
        await self.db.refresh(order)
        return order
```

---

## 4. FastAPI and SQLAlchemy performance rules

### Event loop
- **Use `async def` for every route**, and only await non-blocking I/O inside.
- **Blocking calls** go through `await asyncio.to_thread(fn, ...)`. These include:
  - `requests`, `boto3`, `smtplib`;
  - file I/O on large files, `time.sleep`;
  - CPU-heavy work such as **bcrypt** hashing (about 0.2–0.3s each) and image processing.

  `app/utils/sms_util.py` and `db_admin.migrate_to_head` show the pattern.
- **HTTP clients:** use `httpx.AsyncClient`, never `requests`. Create **one** client in the app `lifespan` and reuse it; a client per request wastes connections and TLS handshakes.
- **Heavy or long work** belongs in a queue (Celery, arq, RQ), not in the request. `BackgroundTasks` is fine only for short, non-critical fire-and-forget work, such as sending an email.

### Database access
- **Sessions:** one session per request via `Depends(get_db)`. Never share a session between concurrent tasks or across requests.
- **No lazy loading.** Async SQLAlchemy raises `MissingGreenlet` when a relationship lazy-loads. Load what you need explicitly:
  ```python
  stmt = select(Order).options(selectinload(Order.items), joinedload(Order.user)).where(Order.user_id == uid)
  ```
  Use `selectinload` for collections and `joinedload` for many-to-one. Setting `lazy="raise"` on relationships makes forgotten loads fail loudly in tests.
- **Avoid N+1 queries.** Never query inside a loop over rows; fetch with `IN (...)` or a join instead.
- **Fetch only what you need.** For big lists, select columns (`select(Order.id, Order.status)`) or use `load_only`.
- **Pagination:**
  - always cap `limit` (`le=100`);
  - for large or fast-growing tables, use keyset pagination (`WHERE id > :last_id ORDER BY id LIMIT n`) instead of large `OFFSET`;
  - avoid `COUNT(*)` on every list request.
- **Indexes:** index foreign keys and anything used in `WHERE`, `ORDER BY` or joins. Use composite indexes for common multi-column filters. Unique constraints for business keys.
- **Writes:** one `commit()` per unit of work, never inside a loop. Use `session.add_all([...])` or `insert(...).values([...])` for bulk inserts. `expire_on_commit=False` is already set, so objects stay usable after commit.
- **Counts and existence checks:** `select(func.count())…`, `exists()`. Don't load rows just to count them.
- **Connection pool (PostgreSQL):** `create_async_engine` in `app/database/db_config.py` uses defaults (5 connections plus 10 overflow per worker). For production, tune with `pool_size`, `max_overflow`, `pool_pre_ping=True` and `pool_recycle`. Expose them as settings. Keep `workers × (pool_size + max_overflow)` below the database's `max_connections`.
- **Logging:** keep `DB_ECHO=false` outside debugging; SQL logging is slow.

### Request and response
- **Always declare `response_model`.** It filters fields (no accidental leaks of `password_hash`), documents the API, and lets Pydantic's compiled core do the serialization. Return ORM objects or dicts; don't build JSON by hand.
- **Keep validators cheap.** No I/O inside Pydantic validators. Do checks like DNS/MX lookups in services, via `to_thread` (see `AuthService.signup`).
- **Big responses:** for large JSON payloads, add `GZipMiddleware(minimum_size=1000)` in `app/middlewares/__init__.py`. Stream files and exports with `StreamingResponse`.
- **Dependencies:** cheap and reused. Expensive lookups (the current user, settings) happen once per request through `Depends`; don't repeat them in the handler.

### Caching
- **What to cache:** expensive, read-heavy, rarely changing data (config lists, aggregates).
- **How:** in a single process, `functools.lru_cache` for pure functions or a small TTL dict. With several workers, Redis (add `redis` to requirements, an async client created in `lifespan`, and a `REDIS_URL` setting).
- **What not to cache:** per-user data, unless the cache key includes the user ID and you invalidate it on writes.

### Running in production
- Use `python scripts/run_prod.py` (gunicorn + `uvicorn_worker.UvicornWorker`, which uses uvloop and httptools automatically).
- **Workers:** start at about the number of CPU cores (`WORKERS`). Async workers each handle many concurrent requests, so more workers mostly add DB connections.
- **Settings:** `ENVIRONMENT=production` hides error details, makes the admin session cookie HTTPS-only, requires the secrets to be set, and disables the setup wizard, database switching and the table builder.
- **Migrations:** run `alembic upgrade head` as a deploy step **before** starting the new code. Never run it from app startup when several workers start at once.
- **Infrastructure:** put a reverse proxy (nginx, Caddy, a cloud load balancer) in front for TLS, HTTP/2, request size limits and static files.

---

## 5. Security checklist for new code
- **Auth on routes:** every non-public route depends on `get_current_user`, or a stricter dependency. Per-user data is scoped with `user_id=` (CRUD) or an explicit `WHERE`; return 404, not 403, for other users' rows.
- **Secrets:** they only come from `settings` / `.env`, never from code. `.env` is git-ignored.
- **Input validation:** validate with Pydantic (`max_length`, `ge`/`le`, `EmailStr`). Never build SQL strings; use SQLAlchemy expressions.
- **Sensitive fields:** keep values like `password_hash` and tokens out of `Out` schemas. Name such columns so they match the admin's sensitive pattern (`password|hash|secret|token|otp|api_key…`), which keeps them out of search.
- **Development-only tools:** anything that writes files or changes infrastructure is guarded with `settings.is_production`.

---

## 6. Testing
- **Setup:** `pytest -q`. Tests are async (`asyncio_mode = auto`) and use `httpx.AsyncClient` with `ASGITransport` against the real app and a temporary SQLite database.
- **Fixtures** (`tests/conftest.py`):
  - `client`;
  - `make_user(username, password, superuser=, verified=, active=)`;
  - `auth_headers(user)`;
  - `outbox`, which captures emails and SMS so nothing is actually sent;
  - a reset database for every test.
- **What to test** for each resource:
  - the happy path for create, read, update and delete;
  - validation (422);
  - auth (401 without a token);
  - **ownership (another user gets 404)**;
  - one edge case per business rule.
- **Mock external services** at the module that imports them (`monkeypatch.setattr("app.services.x.send_email", fake)`).
- **Isolation:** never point tests at the real `.env` or database. Don't assert the exact set of tables or migrations, because the project keeps growing.
- **Migrations:** after model changes, `tests/test_migrations.py` (`alembic check`) fails until a migration exists. That's intentional.

---

## 7. Definition of done
- [ ] Routes are `async`, thin, declare `response_model`, and use auth dependencies.
- [ ] No blocking calls on the event loop (`to_thread` or a queue for sync or CPU-heavy work).
- [ ] Relationships are loaded explicitly; there are no N+1 queries; page sizes are capped.
- [ ] Indexes exist on foreign keys and on filtered or sorted columns.
- [ ] A migration has been generated and reviewed; `alembic upgrade head` and `alembic check` are clean.
- [ ] Tests are added and `pytest -q` is green.
- [ ] Any new settings are added to `Settings` and `.env.example`; no secrets in code.
- [ ] The README is updated if behaviour or commands changed; a **History** entry has been added to `CLAUDE.md`.

---

## 8. Known performance debt in the current code
- **bcrypt blocks the event loop.** `Hash.hash` / `Hash.verify` run directly on the event loop in `AuthService` (signup, login, reset), `services/bootstrap.py`, and the admin login and "set password" form. Each call takes about 0.2–0.3s, during which the worker serves nothing else.

  **Fix:** add async helpers, e.g. `async def hash_async(p): return await asyncio.to_thread(Hash.hash, p)`, and use them in async code.
- **Engine pool not configured.** `create_async_engine` has no pool settings; add them (section 4) before production on PostgreSQL.
