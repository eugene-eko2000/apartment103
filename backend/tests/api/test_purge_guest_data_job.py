"""The scheduled half of guest data retention.

The rule itself is exercised in test_data_retention.py; what this covers is
the job wrapper — that it is registered daily at the configured time, and that
a failing pass is swallowed rather than allowed to take the job down.
"""

from datetime import date, timedelta

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.jobs import purge_guest_data as job
from app.models.booking import Booking, BookingCancellationPolicy, BookingDateRange
from app.models.cancellation_policy import CancellationRule
from app.models.guest import Guest

pytestmark = pytest.mark.anyio


class TestPurgeGuestDataJob:
    async def test_wipes_a_guest_whose_window_has_run_out(self, client, guest):
        # Dated relative to today rather than pinned, because the job takes no
        # as_of — it is the one caller that always means "now".
        long_ago = date.today() - timedelta(days=365)
        booking = Booking(
            guest=guest,
            status="Active",
            date_ranges=[
                BookingDateRange(begin_date=long_ago, end_date=long_ago, price=100)
            ],
            cancellation_policy=BookingCancellationPolicy(
                name="Flexible",
                rules=[CancellationRule(days_before_checkin=1, refund_percentage=1.0)],
            ),
        )
        await booking.insert()

        assert await job.purge_guest_data() == 1
        assert (await Guest.get(guest.id)).is_redacted

    async def test_a_failing_pass_is_swallowed(self, monkeypatch, client):
        async def boom() -> int:
            raise RuntimeError("mongo is having a moment")

        monkeypatch.setattr(job, "purge_expired_guest_data", boom)

        assert await job.purge_guest_data() == 0

    async def test_registers_on_the_scheduler_at_the_configured_time(self):
        scheduler = AsyncIOScheduler()
        job.register(scheduler)

        registered = scheduler.get_job(job.JOB_ID)
        assert registered is not None
        fields = {field.name: str(field) for field in registered.trigger.fields}
        assert fields["hour"] == str(settings.guest_data_retention_sweep_hour)
        assert fields["minute"] == str(settings.guest_data_retention_sweep_minute)
        # One pass at a time, and at most one catch-up run after a restart.
        assert registered.max_instances == 1
        assert registered.coalesce is True
