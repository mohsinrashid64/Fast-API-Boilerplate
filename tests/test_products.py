from tests.conftest import auth_headers

PRODUCT = {"name": "Widget", "price": 9.99, "description": "A widget", "stock": 3}


async def test_requires_auth(client):
    assert (await client.get("/products/")).status_code == 401
    r = await client.get("/products/", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


async def test_owner_crud(client, make_user):
    alice = await make_user("alice")
    h = auth_headers(alice)

    r = await client.post("/products/", json=PRODUCT, headers=h)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["user_id"] == alice.id

    r = await client.patch(f"/products/{pid}", json={"stock": 10}, headers=h)
    assert r.json()["stock"] == 10
    assert r.json()["name"] == "Widget"  # untouched by partial update

    r = await client.put(f"/products/{pid}", json={**PRODUCT, "name": "Gadget"}, headers=h)
    assert r.json()["name"] == "Gadget"

    r = await client.get("/products/", headers=h)
    assert [p["id"] for p in r.json()] == [pid]

    assert (await client.delete(f"/products/{pid}", headers=h)).status_code == 200
    assert (await client.get(f"/products/{pid}", headers=h)).status_code == 404


async def test_other_users_cannot_touch_product(client, make_user):
    alice = await make_user("alice")
    bob = await make_user("bob")
    pid = (await client.post("/products/", json=PRODUCT, headers=auth_headers(alice))).json()["id"]
    hb = auth_headers(bob)

    assert (await client.get(f"/products/{pid}", headers=hb)).status_code == 404
    assert (await client.patch(f"/products/{pid}", json={"price": 0}, headers=hb)).status_code == 404
    assert (await client.put(f"/products/{pid}", json=PRODUCT, headers=hb)).status_code == 404
    assert (await client.delete(f"/products/{pid}", headers=hb)).status_code == 404
    assert (await client.get("/products/", headers=hb)).json() == []

    r = await client.get(f"/products/{pid}", headers=auth_headers(alice))
    assert r.json()["price"] == PRODUCT["price"]


async def test_users_list_is_superuser_only(client, make_user):
    normal = await make_user("normal")
    admin = await make_user("root", superuser=True)

    assert (await client.get("/users")).status_code == 401
    assert (await client.get("/users", headers=auth_headers(normal))).status_code == 403
    r = await client.get("/users", headers=auth_headers(admin))
    assert r.status_code == 200
    assert {u["username"] for u in r.json()} == {"normal", "root"}
