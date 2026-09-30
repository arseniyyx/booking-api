from httpx import AsyncClient


async def test_admin_manages_resources(client: AsyncClient, admin) -> None:
    r = await client.post("/resources", json={"name": "Desk 1"}, headers=admin)
    assert r.status_code == 201
    rid = r.json()["id"]

    r = await client.patch(f"/resources/{rid}", json={"is_active": False}, headers=admin)
    assert r.json()["is_active"] is False

    listed = (await client.get("/resources", headers=admin)).json()
    assert listed["total"] == 0
    listed = (await client.get("/resources?include_inactive=true", headers=admin)).json()
    assert listed["total"] == 1

    assert (await client.delete(f"/resources/{rid}", headers=admin)).status_code == 204
    assert (await client.get(f"/resources/{rid}", headers=admin)).status_code == 404


async def test_regular_user_cannot_create(client: AsyncClient, make_user) -> None:
    user = await make_user()
    r = await client.post("/resources", json={"name": "Desk 1"}, headers=user)
    assert r.status_code == 403


async def test_duplicate_name(client: AsyncClient, admin) -> None:
    await client.post("/resources", json={"name": "Desk 1"}, headers=admin)
    r = await client.post("/resources", json={"name": "Desk 1"}, headers=admin)
    assert r.status_code == 409


async def test_pagination(client: AsyncClient, admin) -> None:
    for i in range(5):
        await client.post("/resources", json={"name": f"Room {i}"}, headers=admin)
    page = (await client.get("/resources?limit=2&offset=2", headers=admin)).json()
    assert page["total"] == 5
    assert [r["name"] for r in page["items"]] == ["Room 2", "Room 3"]
