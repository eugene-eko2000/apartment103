"""The scheduled half of the temporary block.

The sweep itself is exercised in test_availability.py; what this covers is
the job wrapper around it — that it is registered on the shared scheduler at
the configured interval, and that a failing pass is swallowed rather than
allowed to take the job down (APScheduler would otherwise keep firing it into
the same exception, and a background failure must not become the reason the
dates never come back).
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.jobs import expire_pending_bookings as job
from app.models.booking import Booking, BookingCancellationPolicy, BookingDateRange
from app.models.cancellation_policy import CancellationRule
from app.services import availability

pytestmark = pytest.mark.anyio


async def _pending(guest, begin: str, end: str, *, expires_in_minutes: float) -> Booking:
    booking = Booking(
        guest=guest,
        date_ranges=[
            BookingDateRange(
                begin_date=date.fromisoformat(begin), end_date=date.fromisoformat(end), price=100
            )
        ],
        cancellation_policy=BookingCancellationPolicy(
            name="Flexible", rules=[CancellationRule(days_before_checkin=1, refund_percentage=1.0)]
        ),
        pending_expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
    )
    await booking.insert()
    return booking


class TestExpirePendingBookingsJob:
    async def test_removes_lapsed_bookings_and_leaves_live_ones(self, client, guest, other_guest):
        lapsed = await _pending(guest, "2026-09-01", "2026-09-05", expires_in_minutes=-1)
        live = await _pending(other_guest, "2026-10-01", "2026-10-05", expires_in_minutes=5)

        assert await job.expire_pending_bookings() == 1
        assert await Booking.get(lapsed.id) is None
        assert await Booking.get(live.id) is not None

    async def test_a_failing_pass_is_swallowed(self, monkeypatch, client):
        async def boom() -> int:
            raise RuntimeError("mongo is having a moment")

        monkeypatch.setattr(availability, "expire_pending_bookings", boom)
        monkeypatch.setattr(job, "sweep_expired_pending_bookings", boom)

        assert await job.expire_pending_bookings() == 0

    async def test_registers_on_the_scheduler_at_the_configured_interval(self):
        scheduler = AsyncIOScheduler()
        job.register(scheduler)

        registered = scheduler.get_job(job.JOB_ID)
        assert registered is not None
        assert registered.trigger.interval == timedelta(
            minutes=settings.pending_booking_sweep_interval_minutes
        )
        # One pass at a time, and at most one catch-up run after a restart.
        assert registered.max_instances == 1
        assert registered.coalesce is True
