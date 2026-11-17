"""Relationship dropdowns in admin forms: automatic, list-on-open, searchable, paged."""

from app.admin.relations import auto_ajax_refs, searchable_columns
from app.admin.views import ALL_VIEWS
from app.database import Base
from app.models import OTP, Product, User, UserAuth


async def _login(client, make_user):
    await make_user("root", "password123", superuser=True)
    r = await client.post("/admin/login", data={"username": "root", "password": "password123"})
    assert r.status_code == 302


def test_every_relationship_gets_a_picker():
    for view in ALL_VIEWS:
        refs = auto_ajax_refs(view.model)
        from sqlalchemy import inspect

        assert set(refs) == {rel.key for rel in inspect(view.model).relationships}, view.__name__
    assert "user" in auto_ajax_refs(Product) and "products" in auto_ajax_refs(User)


def test_sensitive_columns_are_never_searchable():
    assert "password_hash" not in searchable_columns(UserAuth)
    assert "oauth_access_token" not in searchable_columns(UserAuth)
    assert "otp_code" not in searchable_columns(OTP)
    assert {"id", "username", "email"} <= set(searchable_columns(User))


async def test_owner_picker_lists_users_without_typing(client, make_user):
    await _login(client, make_user)
    await make_user("alice")
    r = await client.get("/admin/product/ajax/lookup", params={"name": "user"})
    assert r.status_code == 200
    body = r.json()
    assert {item["text"] for item in body["results"]} == {"alice", "root"}
    assert body["pagination"]["more"] is False


async def test_picker_search_and_paging(client, make_user):
    await _login(client, make_user)
    for i in range(25):
        await make_user(f"user{i:02d}")

    page1 = (await client.get("/admin/product/ajax/lookup", params={"name": "user", "page": 1})).json()
    page2 = (await client.get("/admin/product/ajax/lookup", params={"name": "user", "page": 2})).json()
    assert len(page1["results"]) == 20 and page1["pagination"]["more"] is True
    assert len(page2["results"]) == 6 and page2["pagination"]["more"] is False  # 25 + root
    assert not {r["id"] for r in page1["results"]} & {r["id"] for r in page2["results"]}

    found = (await client.get("/admin/product/ajax/lookup", params={"name": "user", "term": "user07"})).json()
    assert [r["text"] for r in found["results"]] == ["user07"]


async def test_picker_rejects_unknown_relation_and_anonymous(client, make_user):
    assert (await client.get("/admin/product/ajax/lookup", params={"name": "user"})).status_code == 302
    await _login(client, make_user)
    assert (await client.get("/admin/product/ajax/lookup", params={"name": "nope"})).status_code == 400


async def test_create_product_via_picker_value(client, make_user):
    await _login(client, make_user)
    alice = await make_user("alice")
    r = await client.post(
        "/admin/product/create",
        data={"name": "Lamp", "price": "9.5", "stock": "2", "user": str(alice.id), "save": "Save"},
    )
    assert r.status_code == 302


def test_default_label_for_models_without_str():
    product = Product(name="Desk")
    otp = OTP(id=7, otp_code="123456")
    assert Base.__str__(product) == "Desk"  # uses a name-like column
    assert Base.__str__(otp).startswith("OTP #")  # falls back to the model name + key
