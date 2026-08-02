"""Server-side cancellation-refund math: what fraction of a booking is
refundable as of a given date, given its cancellation policy.

Mirrors `applicableRefundPercentage` in frontend/src/lib/refund.ts (kept
there for the instant UI preview only) — the two must stay in sync. This
module only answers "what fraction is refundable"; turning that into actual
charge amounts and dates is app.services.charge_schedule, which is what
actually decides what Stripe charges.
"""

from datetime import date

from app.models.booking import Booking
from app.models.cancellation_policy import CancellationRule


def days_before_checkin(booking: Booking, as_of: date) -> int:
    """Days between as_of and the stay's check-in (earliest date_range.begin_date)."""
    check_in = min(date_range.begin_date for date_range in booking.date_ranges)
    return (check_in - as_of).days


def applicable_refund_percentage(rules: list[CancellationRule], days_before_check_in: int) -> float:
    """The fraction refundable if cancelled today, given `days_before_check_in` days left.

    Sorted by descending threshold, the first rule at or below the actual
    days-before-check-in wins. Fewer days left than the smallest threshold
    (or no rules at all) falls through to a 0% refund.
    """
    if not rules:
        return 0.0
    for rule in sorted(rules, key=lambda r: r.days_before_checkin, reverse=True):
        if days_before_check_in >= rule.days_before_checkin:
            return rule.refund_percentage
    return 0.0
