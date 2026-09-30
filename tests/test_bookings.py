import asyncio

from httpx import AsyncClient

from tests.conftest import slot


async def book(client: AsyncClient, headers, resource_id: int, s: dict, **extra):
    return await client.post(
        "/bookings", json={"resource_id": resource_id, **s, **extra}, headers=headers
    )


async def test_create_and_list(client: AsyncClient, make_user, resource_id) -> None:
    user = await make_user()
    r = await book(client, user, resource_id, slot(24), note="standup")
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "confirmed"

    page = (await client.get("/bookings", headers=user)).json()
    assert page["total"] == 1
    assert page["items"][0]["note"] == "standup"


async def test_overlap_rejected(client: AsyncClient, make_user, resource_id) -> None:
    user = await make_user()
    assert (await book(client, user, resource_id, slot(24, 2))).status_code == 201
    # Starts inside the existing booking
    r = await book(client, user, resource_id, slot(25, 2))
    assert r.status_code == 409
    assert "already booked" in r.json()["detail"]


async def test_back_to_back_allowed(client: AsyncClient, make_user, resource_id) -> None:
    user = await make_user()
    assert (await book(client, user, resource_id, slot(24))).status_code == 201
    assert (await book(client, user, resource_id, slot(25))).status_code == 201


async def test_cancelled_slot_can_be_rebooked(client: AsyncClient, make_user, resource_id) -> None:
    alice = await make_user("alice@example.com")
    bob = await make_user("bob@example.com")
    booking_id = (await book(client, alice, resource_id, slot(24))).json()["id"]

    r = await client.post(f"/bookings/{booking_id}/cancel", headers=alice)
    assert r.json()["status"] == "cancelled"
    # Cancelling twice is a no-op
    assert (await client.post(f"/bookings/{booking_id}/cancel", headers=alice)).status_code == 200

    assert (await book(client, bob, resource_id, slot(24))).status_code == 201


async def test_concurrent_requests_only_one_wins(
    client: AsyncClient, make_user, resource_id
) -> None:
    """Ten users race for the same slot. The DB constraint must let exactly one through."""
    users = [await make_user(f"racer{i}@example.com") for i in range(10)]
    s = slot(48)
    results = await asyncio.gather(*(book(client, u, resource_id, s) for u in users))
    codes = sorted(r.status_code for r in results)
    assert codes == [201] + [409] * 9


async def test_validation(client: AsyncClient, make_user, resource_id) -> None:
    user = await make_user()
    assert (await book(client, user, resource_id, slot(-2))).status_code == 422  # in the past
    assert (await book(client, user, resource_id, slot(24, 0.1))).status_code == 422  # too short
    assert (await book(client, user, resource_id, slot(24, 12))).status_code == 422  # too long
    s = slot(24)
    reversed_ = {"start_at": s["end_at"], "end_at": s["start_at"]}
    assert (await book(client, user, resource_id, reversed_)).status_code == 422
    naive = {"start_at": "2030-01-01T10:00:00", "end_at": "2030-01-01T11:00:00"}
    assert (await book(client, user, resource_id, naive)).status_code == 422
    assert (await book(client, user, 9999, slot(24))).status_code == 404


async def test_users_cannot_see_each_others_bookings(
    client: AsyncClient, make_user, admin, resource_id
) -> None:
    alice = await make_user("alice@example.com")
    bob = await make_user("bob@example.com")
    booking_id = (await book(client, alice, resource_id, slot(24))).json()["id"]

    assert (await client.get(f"/bookings/{booking_id}", headers=bob)).status_code == 404
    assert (await client.post(f"/bookings/{booking_id}/cancel", headers=bob)).status_code == 404
    assert (await client.get("/bookings", headers=bob)).json()["total"] == 0

    assert (await client.get(f"/bookings/{booking_id}", headers=admin)).status_code == 200
    everyone = (await client.get("/bookings?all_users=true", headers=admin)).json()
    assert everyone["total"] == 1


async def test_busy_slots(client: AsyncClient, make_user, resource_id) -> None:
    user = await make_user()
    s = slot(24)
    await book(client, user, resource_id, s)
    r = await client.get(
        f"/resources/{resource_id}/busy",
        params={"from": slot(20)["start_at"], "to": slot(30)["start_at"]},
        headers=user,
    )
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert set(r.json()[0]) == {"start_at", "end_at"}  # no user details leaked
