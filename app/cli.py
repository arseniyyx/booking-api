"""Small admin CLI: `python -m app.cli promote user@example.com`."""

import asyncio
import sys

from sqlalchemy import update

from app.db import SessionLocal, engine
from app.models import Role, User


async def promote(email: str) -> int:
    async with SessionLocal() as session:
        result = await session.execute(
            update(User).where(User.email == email.lower()).values(role=Role.admin)
        )
        await session.commit()
    await engine.dispose()
    if result.rowcount == 0:
        print(f"No user with email {email}", file=sys.stderr)
        return 1
    print(f"{email} is now an admin")
    return 0


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] != "promote":
        print("usage: python -m app.cli promote <email>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(promote(sys.argv[2])))


if __name__ == "__main__":
    main()
