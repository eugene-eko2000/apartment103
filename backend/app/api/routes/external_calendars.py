from beanie import PydanticObjectId
from fastapi import APIRouter, Depends

from app.api.common import get_or_404
from app.api.crud import make_crud_router
from app.api.deps import require_admin
from app.models.external_calendar import ExternalCalendar
from app.schemas.external_calendar import CalendarSyncResult, ExternalCalendarCreate
from app.services.calendar_sync import (
    SyncResult,
    sync_all_external_calendars,
    sync_external_calendar,
)

router: APIRouter = make_crud_router(
    model=ExternalCalendar,
    create_schema=ExternalCalendarCreate,
    prefix="/external-calendars",
    noun="External calendar",
    id_param="calendar_id",
    tags=["external-calendars"],
    dependencies=[Depends(require_admin)],
)


def _to_schema(result: SyncResult) -> CalendarSyncResult:
    return CalendarSyncResult(
        calendar_id=str(result.calendar_id),
        calendar_name=result.calendar_name,
        status=result.status,
        created=result.created,
        updated=result.updated,
        deleted=result.deleted,
        error=result.error,
    )


# On-demand versions of the scheduled job (app.jobs.sync_calendars). iCal is
# pull-based on both sides, so there's always a window between a reservation
# appearing on Airbnb/Booking.com and our next poll; this is what the host
# presses to close it immediately after noticing one.
@router.post("/sync", response_model=list[CalendarSyncResult])
async def sync_all_calendars() -> list[CalendarSyncResult]:
    return [_to_schema(result) for result in await sync_all_external_calendars()]


@router.post("/{calendar_id}/sync", response_model=CalendarSyncResult)
async def sync_one_calendar(calendar_id: PydanticObjectId) -> CalendarSyncResult:
    calendar = await get_or_404(ExternalCalendar, calendar_id, "External calendar")
    return _to_schema(await sync_external_calendar(calendar))
