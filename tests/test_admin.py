from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Product, User


async def _login(client, username, password) -> int:
    r = await client.post("/admin/login", data={"username": username, "password": password})
    return r.status_code


async def test_admin_requires_login(client):
    r = await client.get("/admin/")
    assert r.status_code == 302
    assert r.headers["location"].endswith("/admin/login")


async def test_non_superuser_cannot_log_in(client, make_user):
    await make_user("normal", "password123")
    assert await _login(client, "normal", "password123") == 400
    assert (await client.get("/admin/")).status_code == 302


async def test_wrong_password_cannot_log_in(client, make_user):
    await make_user("root", "password123", superuser=True)
    assert await _login(client, "root", "wrong-password") == 400


async def test_superuser_can_browse_everything(client, make_user):
    await make_user("root", "password123", superuser=True)
    assert await _login(client, "root@gmail.com", "password123") == 302

    r = await client.get("/admin/")
    assert r.status_code == 200
    assert "Dashboard" in r.text

    for identity in ["user", "user-auth", "product", "otp", "reset-token"]:
        r = await client.get(f"/admin/{identity}/list")
        assert r.status_code == 200, identity
    for identity in ["user", "product"]:
        assert (await client.get(f"/admin/{identity}/create")).status_code == 200


async def test_admin_creates_product_and_user(client, make_user):
    root = await make_user("root", "password123", superuser=True)
    await _login(client, "root", "password123")

    r = await client.post(
        "/admin/product/create",
        data={"name": "Admin Widget", "price": "12.50", "stock": "4", "user": str(root.id), "save": "Save"},
    )
    assert r.status_code == 302, r.text
    async with AsyncSessionLocal() as session:
        product = (await session.execute(select(Product))).scalar_one()
    assert (product.name, product.price, product.user_id) == ("Admin Widget", 12.5, root.id)

    # Create a user with a password from the admin, then log in through the API.
    r = await client.post(
        "/admin/user/create",
        data={"username": "jane", "email": "Jane@Gmail.com", "is_active": "y", "is_verified": "y",
              "password": "janepass123", "save": "Save"},
    )
    assert r.status_code == 302, r.text
    r = await client.post("/auth/login", json={"username_or_email_or_phone": "jane", "password": "janepass123"})
    assert "access_token" in r.json()
    async with AsyncSessionLocal() as session:
        jane = (await session.execute(select(User).where(User.username == "jane"))).scalar_one()
    assert jane.email == "jane@gmail.com"


async def test_admin_cannot_demote_self(client, make_user):
    root = await make_user("root", "password123", superuser=True)
    await _login(client, "root", "password123")
    r = await client.post(
        f"/admin/user/edit/{root.id}",
        data={"username": "root", "email": "root@gmail.com", "is_active": "y", "save": "Save"},
    )
    assert r.status_code == 400
    assert "cannot remove your own" in r.text


async def test_demoted_admin_loses_access_immediately(client, make_user):
    root = await make_user("root", "password123", superuser=True)
    await _login(client, "root", "password123")
    assert (await client.get("/admin/")).status_code == 200

    async with AsyncSessionLocal() as session:
        user = await session.get(User, root.id)
        user.is_superuser = False
        await session.commit()

    assert (await client.get("/admin/")).status_code == 302


async def test_schema_page_requires_login(client):
    r = await client.get("/admin/schema")
    assert r.status_code == 302


async def test_schema_page_shows_every_table(client, make_user):
    await make_user("root", "password123", superuser=True)
    await _login(client, "root", "password123")
    r = await client.get("/admin/schema")
    assert r.status_code == 200
    for table in ["users", "user_auth", "products", "otps", "reset_tokens"]:
        assert f'"name": "{table}"' in r.text


async def test_build_schema_describes_keys_and_relations(make_user):
    from app.admin.schema import build_schema
    from app.database import AsyncSessionLocal

    await make_user("root", superuser=True)
    async with AsyncSessionLocal() as session:
        schema = await build_schema(session)

    tables = {t["name"]: t for t in schema["tables"]}
    # Tables you generate later are fine; the core ones must be there.
    assert set(tables) >= {"users", "user_auth", "products", "otps", "reset_tokens"}
    assert tables["users"]["row_count"] == 1
    users_cols = {c["name"]: c for c in tables["users"]["columns"]}
    assert users_cols["id"]["primary_key"] and users_cols["email"]["unique"]
    assert users_cols["phone_number"]["nullable"] and not users_cols["username"]["nullable"]

    product_fk = next(e for e in schema["edges"] if e["from_table"] == "products")
    assert (product_fk["to_table"], product_fk["to_columns"], product_fk["ondelete"]) == ("users", ["id"], "CASCADE")
    assert product_fk["cardinality"] == "many-to-one"
    assert {r["name"] for r in tables["users"]["relationships"]} == {"auth", "reset_tokens", "otps", "products"}
