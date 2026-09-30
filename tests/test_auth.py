from httpx import AsyncClient


async def test_register_login_me(client: AsyncClient, make_user) -> None:
    headers = await make_user("Alice@Example.com")
    r = await client.get("/users/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "alice@example.com"
    assert r.json()["role"] == "user"


async def test_duplicate_email_rejected(client: AsyncClient, make_user) -> None:
    await make_user("bob@example.com")
    r = await client.post(
        "/auth/register", json={"email": "bob@example.com", "password": "another-password"}
    )
    assert r.status_code == 409


async def test_wrong_password(client: AsyncClient, make_user) -> None:
    await make_user("carol@example.com")
    r = await client.post("/auth/login", data={"username": "carol@example.com", "password": "nope"})
    assert r.status_code == 401


async def test_requires_token(client: AsyncClient) -> None:
    assert (await client.get("/users/me")).status_code == 401
    bad = {"Authorization": "Bearer not-a-jwt"}
    assert (await client.get("/users/me", headers=bad)).status_code == 401
