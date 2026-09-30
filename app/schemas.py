from datetime import datetime
from typing import Generic, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models import BookingStatus, Role


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth / users ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class UserOut(ORMModel):
    id: int
    email: EmailStr
    role: Role
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- resources ---
class ResourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class ResourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    is_active: bool | None = None


class ResourceOut(ORMModel):
    id: int
    name: str
    description: str
    is_active: bool


class BusySlot(BaseModel):
    start_at: datetime
    end_at: datetime


# --- bookings ---
class BookingCreate(BaseModel):
    resource_id: int
    start_at: AwareDatetime
    end_at: AwareDatetime
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def check_order(self) -> "BookingCreate":
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class BookingOut(ORMModel):
    id: int
    resource_id: int
    user_id: int
    start_at: datetime
    end_at: datetime
    status: BookingStatus
    note: str
    created_at: datetime


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
