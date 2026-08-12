"""Booking charge schedule: turning a cancellation policy into calendar
dates and amounts to charge.

`build_charge_schedule` is the one place that does this conversion —
computed once, at booking time, and stored on the booking. Everything
downstream (the daily reconciliation job, cancellation settlement, the
initial/retry payment endpoints) just reads that stored schedule via the
helpers below instead of re-deriving amounts from the policy live on every
call. This is the authoritative implementation for anything that moves
money.
"""

from datetime import date, timedelta
from decimal import Decimal

from app.core.money import to_decimal
from app.models.booking import Booking, BookingChargeScheduleEntry
from app.services.cancellation import applicable_refund_percentage

# Rounding across repeated charges/refunds can leave a few hundredths of a
# unit of drift; treat amount_charged as having "covered" a schedule entry
# once it's within a cent of it.
_STATUS_SYNC_EPSILON = Decimal("0.01")


def build_charge_schedule(booking: Booking) -> list[BookingChargeScheduleEntry]:
    """The full timeline of amounts that become non-refundable — and
    therefore chargeable — over the life of the booking, computed once from
    `booking.cancellation_policy.rules` and the stay's check-in date.

    Each entry is the incremental amount that becomes due on `charge_date`.
    Summing due entries reproduces what `applicable_refund_percentage` would
    say is non-refundable as of any given date: a rule's own threshold date
    is still covered by the more lenient (previous) rule, since
    `applicable_refund_percentage` treats `days_before_check_in >=
    rule.days_before_checkin` as inclusive, so the amount it newly requires
    only becomes due the calendar day after that threshold date. A trailing
    entry at check-in is always included unless a rule already covers a 0%
    refund by then, matching `applicable_refund_percentage`'s fallback.
    """
    check_in = min(date_range.begin_date for date_range in booking.date_ranges)
    total_price = booking.total_price
    rules = booking.cancellation_policy.rules

    thresholds = sorted({rule.days_before_checkin for rule in rules}, reverse=True)
    if not thresholds or thresholds[-1] != 0:
        thresholds.append(0)

    schedule: list[BookingChargeScheduleEntry] = []
    due_date = booking.booking_date
    previous_refund_percentage = Decimal("1.00")
    for threshold in thresholds:
        refund_percentage = to_decimal(applicable_refund_percentage(rules, threshold))
        amount = to_decimal(total_price * (previous_refund_percentage - refund_percentage))
        if amount > 0:
            schedule.append(BookingChargeScheduleEntry(charge_date=due_date, amount=amount))
        due_date = check_in - timedelta(days=threshold - 1)
        previous_refund_percentage = refund_percentage
    return schedule


def scheduled_amount_due(schedule: list[BookingChargeScheduleEntry], as_of: date) -> Decimal:
    """Cumulative amount the stored schedule says should be captured by
    `as_of`, regardless of each entry's current status."""
    total = sum((entry.amount for entry in schedule if entry.charge_date <= as_of), Decimal("0.00"))
    return to_decimal(total)


def outstanding_amount(booking: Booking, as_of: date) -> Decimal:
    """What's left to charge as of `as_of`: schedule-due minus what's
    already been captured. The single formula every payment/reconciliation
    path uses to decide how much (if anything) still needs charging."""
    return to_decimal(scheduled_amount_due(booking.charge_schedule, as_of) - to_decimal(booking.amount_charged))


def upcoming_charges(booking: Booking, as_of: date) -> list[BookingChargeScheduleEntry]:
    """Schedule entries not yet due as of `as_of` — the amounts a guest
    should expect to be charged automatically later in the life of the
    booking, beyond whatever is being paid right now."""
    return sorted(
        (entry for entry in booking.charge_schedule if entry.charge_date > as_of),
        key=lambda entry: entry.charge_date,
    )


def sync_charge_schedule_status(booking: Booking) -> None:
    """Keep each schedule entry's pending/done status in sync with
    `amount_charged`. Call this after anything that changes amount_charged
    (a successful charge, a refund) so the schedule always reflects what's
    actually been captured, rather than only the specific entries a given
    charge/refund happened to target.
    """
    cumulative = Decimal("0.00")
    for entry in sorted(booking.charge_schedule, key=lambda entry: entry.charge_date):
        cumulative += entry.amount
        entry.status = "done" if booking.amount_charged >= cumulative - _STATUS_SYNC_EPSILON else "pending"
