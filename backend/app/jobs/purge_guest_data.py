"""Daily job: retire the personal data of guests nobody is serving any more.

The rule and everything behind it live in app.services.data_retention — a
guest whose last stay ended (or whose last booking was cancelled) more than
settings.guest_data_retention_months ago has their identifying fields
overwritten in place, while the booking and payment records that link to them
stay readable.

Unlike the pending-booking sweep, nothing calls this on demand: no request
path has a reason to notice that a guest's retention window lapsed while it
was serving something else, so this job is the only thing that makes it
happen. It runs once a day because the window is measured in months —
checking more often would find the same nothing.

Runs in-process via APScheduler on the shared scheduler in app.jobs.scheduler
(one scheduler per process — see the scaling note in
docs/stripe-payment-design.md). Running it twice over is harmless: a guest
already wiped carries `redacted_at` and is skipped.
"""

import logging

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.services.data_retention import purge_expired_guest_data

logger = logging.getLogger(__name__)

JOB_ID = "purge_expired_guest_data"


async def purge_guest_data() -> int:
    try:
        return await purge_expired_guest_data()
    except Exception:
        # A failed pass must not take the job down. Retention is measured in
        # months, so tomorrow's pass wiping what today's couldn't is not a
        # meaningful delay — whereas APScheduler firing this into the same
        # exception forever would be.
        logger.exception("Failed to purge expired guest data")
        return 0


def register(scheduler: BaseScheduler) -> None:
    scheduler.add_job(
        purge_guest_data,
        CronTrigger(
            hour=settings.guest_data_retention_sweep_hour,
            minute=settings.guest_data_retention_sweep_minute,
        ),
        id=JOB_ID,
        replace_existing=True,
        # One pass at a time, and at most one catch-up run after a restart —
        # rather than one for every day the process was down.
        max_instances=1,
        coalesce=True,
    )
