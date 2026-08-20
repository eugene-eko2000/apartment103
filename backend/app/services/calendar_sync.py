"""Inbound half of calendar sync: external .ics feeds into our Closures.

This is the "external calendar -> our calendar" direction. One pass per
ExternalCalendar: fetch the feed, parse its VEVENTs, and make the closures
imported from that calendar match it exactly — insert what's new, update
what moved, delete what's gone (the OTA-side reservation was cancelled).

Manual closures are never touched: they're the ones with no
external_calendar_id, and every query here is scoped to one calendar's id.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from beanie import PydanticObjectId

from app.core.config import settings
from app.models.closure import Closure
from app.models.external_calendar import ExternalCalendar
from app.services.ics import IcsEvent, parse_calendar

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Outcome of one calendar's pass, as reported back to the admin UI."""

    calendar_id: PydanticObjectId
    calendar_name: str
    status: str  # "ok" | "error"
    created: int = 0
    updated: int = 0
    deleted: int = 0
    error: str | None = None

    @property
    def block_count(self) -> int:
        return self.created + self.updated


async def fetch_calendar_feed(url: str) -> bytes:
    """The raw .ics body at `url`.

    follow_redirects because both Airbnb's and Booking.com's export links
    redirect at least once.
    """
    async with httpx.AsyncClient(
        timeout=settings.calendar_sync_timeout_seconds, follow_redirects=True
    ) as client:
        response = await client.get(url, headers={"Accept": "text/calendar, */*"})
        response.raise_for_status()
        return response.content


async def sync_external_calendar(calendar: ExternalCalendar) -> SyncResult:
    """Pull one calendar's feed and reconcile our closures with it.

    Never raises: a failing feed is recorded on the calendar
    (last_sync_status/last_sync_error) and returned as an error result, so
    one broken URL can't stop the others in a scheduled pass.
    """
    try:
        raw = await fetch_calendar_feed(calendar.url)
        events = parse_calendar(raw)
    except Exception as exc:
        logger.exception("Calendar sync failed for %s (%s)", calendar.name, calendar.url)
        # Deliberately before any write: an unreachable feed must leave the
        # existing closures alone. Treating "I couldn't fetch it" as "it
        # returned nothing" would free up dates that are still booked on the
        # other platform.
        result = SyncResult(
            calendar_id=calendar.id,
            calendar_name=calendar.name,
            status="error",
            error=f"{type(exc).__name__}: {exc}",
        )
        await _record_sync_outcome(calendar, result)
        return result

    result = await _apply_events(calendar, events)
    await _record_sync_outcome(calendar, result)
    logger.info(
        "Calendar sync for %s: %d created, %d updated, %d deleted",
        calendar.name,
        result.created,
        result.updated,
        result.deleted,
    )
    return result


async def _apply_events(calendar: ExternalCalendar, events: list[IcsEvent]) -> SyncResult:
    """Make this calendar's closures match `events` exactly."""
    result = SyncResult(calendar_id=calendar.id, calendar_name=calendar.name, status="ok")
    now = datetime.now(timezone.utc)

    existing = await Closure.find(Closure.external_calendar_id == calendar.id).to_list()
    by_uid = {closure.external_uid: closure for closure in existing}

    for event in events:
        closure = by_uid.pop(event.uid, None)
        if closure is None:
            await Closure(
                platform=calendar.name,
                begin_date=event.begin_date,
                end_date=event.end_date,
                external_calendar_id=calendar.id,
                external_uid=event.uid,
                last_seen_at=now,
            ).insert()
            result.created += 1
            continue
        # A targeted $set rather than Document.save(), matching the rest of
        # the codebase: only the fields this feed owns are rewritten.
        await closure.set(
            {
                Closure.platform: calendar.name,
                Closure.begin_date: event.begin_date,
                Closure.end_date: event.end_date,
                Closure.last_seen_at: now,
            }
        )
        result.updated += 1

    # Whatever is left in by_uid had no VEVENT in this pass, i.e. the
    # reservation behind it was cancelled on the other platform. The design
    # doc reaches this by comparing last_seen_at against the pass start;
    # a set difference over the same data gets there without depending on
    # clock resolution or on every write having succeeded.
    for stale in by_uid.values():
        await stale.delete()
        result.deleted += 1

    return result


async def _record_sync_outcome(calendar: ExternalCalendar, result: SyncResult) -> None:
    await calendar.set(
        {
            ExternalCalendar.last_synced_at: datetime.now(timezone.utc),
            ExternalCalendar.last_sync_status: result.status,
            ExternalCalendar.last_sync_error: result.error,
            ExternalCalendar.last_sync_block_count: (
                result.block_count if result.status == "ok" else calendar.last_sync_block_count
            ),
        }
    )


async def sync_all_external_calendars() -> list[SyncResult]:
    """One pass over every configured calendar."""
    calendars = await ExternalCalendar.find_all().to_list()
    return [await sync_external_calendar(calendar) for calendar in calendars]
