"""Daily job: keep each active booking's amount_charged in sync with what's
currently accrued as non-refundable under its cancellation policy.

Runs in-process via APScheduler on the shared scheduler in
app.jobs.scheduler (no separate worker/cron infra exists yet — see
docs/stripe-payment-design.md for the scaling note if this ever runs on more
than one backend instance, which would fire the job once per instance).
"""

import logging
from datetime import date, datetime, timezone

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger

from app.models.booking import Booking
from app.services.payment_reconciliation import charge_outstanding_balance

logger = logging.getLogger(__name__)

JOB_ID = "reconcile_booking_payments"


async def reconcile_booking_payments() -> None:
    bookings = await Booking.find(Booking.status == "Active", fetch_links=True).to_list()
    checked = 0
    charged = 0
    for booking in bookings:
        checked += 1
        before = booking.amount_charged
        try:
            # charge_outstanding_balance no-ops on its own for bookings with
            # nothing outstanding or no saved card yet, so it's safe/cheap to
            # call for every active booking rather than pre-filtering here.
            await charge_outstanding_balance(
                booking,
                reason="scheduled_accrual",
                idempotency_key=f"scheduled_accrual:{booking.id}:{date.today().isoformat()}",
            )
            if booking.amount_charged != before:
                charged += 1
        except Exception:
            logger.exception("Failed to reconcile payment for booking %s", booking.id)
        # A targeted $set, not Document.save(): save() replaces the whole
        # document, so stamping this timestamp would rewrite every charge,
        # schedule entry and webhook-event reference on the booking — and
        # would write back this in-memory copy over anything
        # charge_outstanding_balance had just persisted.
        await booking.set({Booking.last_payment_check_at: datetime.now(timezone.utc)})
    logger.info("Payment reconciliation: checked=%d bookings, charged=%d", checked, charged)


def register(scheduler: BaseScheduler) -> None:
    scheduler.add_job(
        reconcile_booking_payments,
        CronTrigger(hour=6, minute=0),
        id=JOB_ID,
        replace_existing=True,
    )
