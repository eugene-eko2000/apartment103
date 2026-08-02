from datetime import date

from app.models.booking import BookingDateRange
from app.models.cancellation_policy import CancellationRule
from app.services.cancellation import applicable_refund_percentage, days_before_checkin
from tests.booking_factories import booking


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
        b = booking([], date(2026, 8, 10))
        b.date_ranges.append(BookingDateRange(begin_date=date(2026, 8, 20), end_date=date(2026, 8, 25), price=100))
        assert days_before_checkin(b, date(2026, 8, 1)) == 9
