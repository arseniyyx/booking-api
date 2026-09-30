import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/booking_test"
)
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-bytes-long")

from collections.abc import AsyncIterator, Awaitable, Callable  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text, update  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Run the real migrations once, so tests exercise the same schema as production."""
    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = os.environ["DATABASE_URL"]
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    yield
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE bookings, resources, users RESTART IDENTITY CASCADE"))


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


UserFactory = Callable[..., Awaitable[dict[str, str]]]


@pytest.fixture
def make_user(client: AsyncClient) -> UserFactory:
    """Register a user and return auth headers for them."""

    async def _make(email: str = "user@example.com", admin: bool = False) -> dict[str, str]:
        password = "correct-horse-battery"
        r = await client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code == 201, r.text
        if admin:
            async with SessionLocal() as s:
                await s.execute(update(User).where(User.email == email).values(role=Role.admin))
                await s.commit()
        r = await client.post("/auth/login", data={"username": email, "password": password})
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _make


@pytest.fixture
async def admin(make_user: UserFactory) -> dict[str, str]:
    return await make_user("admin@example.com", admin=True)


@pytest.fixture
async def resource_id(client: AsyncClient, admin: dict[str, str]) -> int:
    r = await client.post("/resources", json={"name": "Room A"}, headers=admin)
    return r.json()["id"]


def slot(hours_from_now: float, duration_h: float = 1) -> dict[str, str]:
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(
        hours=hours_from_now
    )
    return {
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(hours=duration_h)).isoformat(),
    }
