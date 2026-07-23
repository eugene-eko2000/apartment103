from datetime import date

from app.models.booking import Booking, BookingCancellationPolicy, BookingDateRange
from app.models.cancellation_policy import CancellationRule
from app.models.guest import Guest, ResidenceAddress
from app.services.cancellation import (
    accrued_non_refundable_amount,
    applicable_refund_percentage,
    days_before_checkin,
)


def _guest() -> Guest:
    return Guest(
        family_name="Test",
        first_name="Guest",
        residence_address=ResidenceAddress(street_address="1 St", zip="0000", city="City", country="CH"),
        phone_number="+41000000000",
        email="test@example.com",
    )


def _booking(rules: list[CancellationRule], begin_date: date, price: float = 1000.0) -> Booking:
    return Booking(
        guest=_guest(),
        currency="CHF",
        date_ranges=[BookingDateRange(begin_date=begin_date, end_date=begin_date, price=price)],
        cancellation_policy=BookingCancellationPolicy(name="Test", rules=rules),
    )


class TestApplicableRefundPercentage:
    def test_no_rules_returns_zero(self):
        assert applicable_refund_percentage([], 30) == 0.0

    def test_highest_matching_threshold_wins(self):
        rules = [
            CancellationRule(days_before_checkin=30, refund_percentage=1.0),
            CancellationRule(days_before_checkin=7, refund_percentage=0.5),
            CancellationRule(days_before_checkin=0, refund_percentage=0.0),
        ]
        assert applicable_refund_percentage(rules, 45) == 1.0
        assert applicable_refund_percentage(rules, 30) == 1.0
        assert applicable_refund_percentage(rules, 15) == 0.5
        assert applicable_refund_percentage(rules, 7) == 0.5
        assert applicable_refund_percentage(rules, 3) == 0.0
        assert applicable_refund_percentage(rules, 0) == 0.0

    def test_fewer_days_than_smallest_threshold_is_zero(self):
        rules = [CancellationRule(days_before_checkin=30, refund_percentage=1.0)]
        assert applicable_refund_percentage(rules, 10) == 0.0

    def test_rule_order_does_not_matter(self):
        rules = [
            CancellationRule(days_before_checkin=0, refund_percentage=0.0),
            CancellationRule(days_before_checkin=30, refund_percentage=1.0),
        ]
        assert applicable_refund_percentage(rules, 45) == 1.0


class TestDaysBeforeCheckin:
    def test_computes_days_from_earliest_date_range(self):
        booking = _booking([], date(2026, 8, 10))
        booking.date_ranges.append(
            BookingDateRange(begin_date=date(2026, 8, 20), end_date=date(2026, 8, 25), price=100)
        )
        assert days_before_checkin(booking, date(2026, 8, 1)) == 9


class TestAccruedNonRefundableAmount:
    def test_fully_refundable_zone_is_zero(self):
        rules = [CancellationRule(days_before_checkin=30, refund_percentage=1.0)]
        booking = _booking(rules, date(2026, 9, 1), price=1000.0)
        assert accrued_non_refundable_amount(booking, date(2026, 8, 1)) == 0.0

    def test_partial_fee_zone(self):
        rules = [
            CancellationRule(days_before_checkin=30, refund_percentage=1.0),
            CancellationRule(days_before_checkin=7, refund_percentage=0.5),
        ]
        booking = _booking(rules, date(2026, 8, 20), price=1000.0)
        assert accrued_non_refundable_amount(booking, date(2026, 8, 10)) == 500.0

    def test_fully_non_refundable_zone_equals_total(self):
        rules = [CancellationRule(days_before_checkin=7, refund_percentage=1.0)]
        booking = _booking(rules, date(2026, 8, 5), price=1000.0)
        assert accrued_non_refundable_amount(booking, date(2026, 8, 4)) == 1000.0
