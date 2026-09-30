from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/booking"
    # Override via JWT_SECRET in any real deployment.
    jwt_secret: str = "dev-only-secret-change-me-in-production-please"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60

    # Business rules for bookings
    min_booking_minutes: int = 15
    max_booking_hours: int = 8


@lru_cache
def get_settings() -> Settings:
    return Settings()
