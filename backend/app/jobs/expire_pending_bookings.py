"""Recurring job: drop Pending bookings whose hold on the dates has lapsed.

A booking is created — and starts blocking its nights — the moment a guest
reaches checkout (see app.services.availability). Most of those guests either
pay or cancel; the rest simply close the tab, and their nights have to come
back to the calendar on their own. That is what this job is for: every
settings.pending_booking_sweep_interval_minutes it deletes the bookings whose
settings.pending_booking_ttl_minutes window has run out.

It is not the only thing standing between an abandoned checkout and the dates
it holds. Every path that reads or claims availability calls the same
`expire_pending_bookings` first, so no booking or calendar answer is ever
wrong just because this job hasn't run lately. What the job adds is that the
release happens even when nobody asks — so the public calendar frees the
dates up on its own, rather than at the moment the next guest happens to
collide with them.

Runs in-process via APScheduler on the shared scheduler in app.jobs.scheduler
(one scheduler per process — see the scaling note in
docs/stripe-payment-design.md). Running it twice over is harmless: the sweep
is a single conditional bulk delete.
"""

import logging

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.services.availability import expire_pending_bookings as sweep_expired_pending_bookings

logger = logging.getLogger(__name__)

JOB_ID = "expire_pending_bookings"


async def expire_pending_bookings() -> int:
    try:
        return await sweep_expired_pending_bookings()
    except Exception:
        # A failed pass must not take the job down — the next tick, or the
        # next availability check, will clear the same bookings.
        logger.exception("Failed to expire pending bookings")
        return 0


def register(scheduler: BaseScheduler) -> None:
    scheduler.add_job(
        expire_pending_bookings,
        IntervalTrigger(minutes=settings.pending_booking_sweep_interval_minutes),
        id=JOB_ID,
        replace_existing=True,
        # One pass at a time, and at most one catch-up run after a busy
        # stretch or a restart — rather than firing once for every interval
        # the process slept through.
        max_instances=1,
        coalesce=True,
    )
