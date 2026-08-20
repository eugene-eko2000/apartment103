"""The single APScheduler instance the backend's background jobs run on.

Lives here rather than next to any one job so adding a second job doesn't
mean importing an unrelated module for its scheduler. Job modules stay
scheduler-agnostic: each exposes a `register(scheduler)` that this module
calls at startup.

One scheduler per process, so running more than one backend instance would
fire every job once per instance — see the scaling note in
docs/stripe-payment-design.md.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    if scheduler.running:
        return
    # Imported here, not at module scope: the job modules pull in the model
    # and service stack, and they in turn should be able to import this
    # module for the scheduler without a cycle.
    from app.jobs import reconcile_payments, sync_calendars

    reconcile_payments.register(scheduler)
    sync_calendars.register(scheduler)
    scheduler.start()
    logger.info("Scheduler started with jobs: %s", [job.id for job in scheduler.get_jobs()])
