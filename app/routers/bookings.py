from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.deps import CurrentUser, SessionDep
from app.models import Booking, BookingStatus, Resource, Role, User
from app.schemas import BookingCreate, BookingOut, Page

router = APIRouter(prefix="/bookings", tags=["bookings"])

EXCLUSION_VIOLATION = "23P01"


def _validate_window(body: BookingCreate) -> None:
    settings = get_settings()
    duration = body.end_at - body.start_at
    if body.start_at <= datetime.now(UTC):
        raise HTTPException(422, "Booking must start in the future")
    if duration < timedelta(minutes=settings.min_booking_minutes):
        raise HTTPException(
            422,
            f"Booking must be at least {settings.min_booking_minutes} minutes",
        )
    if duration > timedelta(hours=settings.max_booking_hours):
        raise HTTPException(
            422,
            f"Booking must be at most {settings.max_booking_hours} hours",
        )


async def _get_visible_booking(session: SessionDep, booking_id: int, user: User) -> Booking:
    booking = await session.get(Booking, booking_id)
    # Return 404 rather than 403 so users cannot probe other people's booking ids.
    if booking is None or (user.role != Role.admin and booking.user_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    return booking


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
async def create_booking(body: BookingCreate, session: SessionDep, user: CurrentUser) -> Booking:
    _validate_window(body)
    resource = await session.get(Resource, body.resource_id)
    if resource is None or not resource.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found")

    booking = Booking(
        resource_id=body.resource_id,
        user_id=user.id,
        start_at=body.start_at,
        end_at=body.end_at,
        note=body.note,
    )
    session.add(booking)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if getattr(exc.orig, "sqlstate", None) == EXCLUSION_VIOLATION:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Resource is already booked for this time"
            ) from None
        raise
    await session.refresh(booking)
    return booking


@router.get("", response_model=Page[BookingOut])
async def list_bookings(
    session: SessionDep,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    booking_status: Annotated[BookingStatus | None, Query(alias="status")] = None,
    resource_id: int | None = None,
    all_users: Annotated[
        bool, Query(description="Admins only: include everyone's bookings")
    ] = False,
) -> dict:
    query = select(Booking)
    if not (all_users and user.role == Role.admin):
        query = query.where(Booking.user_id == user.id)
    if booking_status is not None:
        query = query.where(Booking.status == booking_status)
    if resource_id is not None:
        query = query.where(Booking.resource_id == resource_id)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(query.order_by(Booking.start_at).limit(limit).offset(offset))
    return {"items": rows.all(), "total": total, "limit": limit, "offset": offset}


@router.get("/{booking_id}", response_model=BookingOut)
async def get_booking(booking_id: int, session: SessionDep, user: CurrentUser) -> Booking:
    return await _get_visible_booking(session, booking_id, user)


@router.post("/{booking_id}/cancel", response_model=BookingOut)
async def cancel_booking(booking_id: int, session: SessionDep, user: CurrentUser) -> Booking:
    booking = await _get_visible_booking(session, booking_id, user)
    if booking.status == BookingStatus.cancelled:
        return booking  # idempotent
    if user.role != Role.admin and booking.start_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot cancel a booking that has started")
    booking.status = BookingStatus.cancelled
    await session.commit()
    await session.refresh(booking)
    return booking
