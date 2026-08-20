"""Recurring job: pull every ExternalCalendar's .ics feed into our closures.

The inbound half of docs/calendar-sync-design.md. Runs in-process via
APScheduler, every settings.calendar_sync_interval_minutes — Airbnb and
Booking.com regenerate their exports only a few times a day, so a tighter
interval wouldn't make this more current, and a looser one would widen the
window in which a stay booked there is still bookable here.
"""

import logging

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.services.calendar_sync import sync_all_external_calendars

logger = logging.getLogger(__name__)

JOB_ID = "sync_external_calendars"


async def sync_external_calendars() -> None:
    results = await sync_all_external_calendars()
    if not results:
        return
    failed = [result for result in results if result.status == "error"]
    logger.info(
        "Calendar sync pass: %d calendars, %d created, %d updated, %d deleted, %d failed",
        len(results),
        sum(result.created for result in results),
        sum(result.updated for result in results),
        sum(result.deleted for result in results),
        len(failed),
    )


def register(scheduler: BaseScheduler) -> None:
    scheduler.add_job(
        sync_external_calendars,
        IntervalTrigger(minutes=settings.calendar_sync_interval_minutes),
        id=JOB_ID,
        replace_existing=True,
        # One pass at a time: a slow feed must not let the next tick start a
        # second, concurrent reconciliation of the same closures.
        max_instances=1,
        # Catch up with at most one run if the process was busy/restarting,
        # instead of firing every interval it slept through.
        coalesce=True,
    )
