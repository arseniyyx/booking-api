from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import AwareDatetime
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.deps import AdminUser, CurrentUser, SessionDep
from app.models import Booking, BookingStatus, Resource
from app.schemas import BusySlot, Page, ResourceCreate, ResourceOut, ResourceUpdate

router = APIRouter(prefix="/resources", tags=["resources"])


async def _get_or_404(session: SessionDep, resource_id: int) -> Resource:
    resource = await session.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found")
    return resource


@router.get("", response_model=Page[ResourceOut])
async def list_resources(
    session: SessionDep,
    _: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_inactive: bool = False,
) -> dict:
    query = select(Resource)
    if not include_inactive:
        query = query.where(Resource.is_active.is_(True))
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(query.order_by(Resource.id).limit(limit).offset(offset))
    return {"items": rows.all(), "total": total, "limit": limit, "offset": offset}


@router.post("", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
async def create_resource(body: ResourceCreate, session: SessionDep, _: AdminUser) -> Resource:
    resource = Resource(name=body.name, description=body.description)
    session.add(resource)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Resource name already exists") from None
    await session.refresh(resource)
    return resource


@router.get("/{resource_id}", response_model=ResourceOut)
async def get_resource(resource_id: int, session: SessionDep, _: CurrentUser) -> Resource:
    return await _get_or_404(session, resource_id)


@router.patch("/{resource_id}", response_model=ResourceOut)
async def update_resource(
    resource_id: int, body: ResourceUpdate, session: SessionDep, _: AdminUser
) -> Resource:
    resource = await _get_or_404(session, resource_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(resource, field, value)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Resource name already exists") from None
    await session.refresh(resource)
    return resource


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(resource_id: int, session: SessionDep, _: AdminUser) -> None:
    resource = await _get_or_404(session, resource_id)
    await session.delete(resource)
    await session.commit()


@router.get("/{resource_id}/busy", response_model=list[BusySlot])
async def busy_slots(
    resource_id: int,
    session: SessionDep,
    _: CurrentUser,
    start: Annotated[AwareDatetime, Query(alias="from")],
    end: Annotated[AwareDatetime, Query(alias="to")],
) -> list[Booking]:
    """Confirmed bookings overlapping [from, to). Other users' details are not exposed."""
    await _get_or_404(session, resource_id)
    if end <= start:
        raise HTTPException(422, "'to' must be after 'from'")
    rows = await session.scalars(
        select(Booking)
        .where(
            Booking.resource_id == resource_id,
            Booking.status == BookingStatus.confirmed,
            Booking.start_at < end,
            Booking.end_at > start,
        )
        .order_by(Booking.start_at)
    )
    return list(rows)
