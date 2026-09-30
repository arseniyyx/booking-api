from fastapi import FastAPI
from sqlalchemy import text

from app.db import SessionLocal
from app.routers import auth, bookings, resources

app = FastAPI(
    title="Booking API",
    description="Book shared resources (rooms, desks, equipment) without double bookings.",
    version="0.1.0",
)
app.include_router(auth.router)
app.include_router(resources.router)
app.include_router(bookings.router)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    async with SessionLocal() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok"}
