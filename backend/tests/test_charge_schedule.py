from datetime import date

from app.models.cancellation_policy import CancellationRule
from app.services.charge_schedule import (
    build_charge_schedule,
    outstanding_amount,
    scheduled_amount_due,
    sync_charge_schedule_status,
    upcoming_charges,
)
from tests.booking_factories import booking


class TestBuildChargeSchedule:
    """The schedule is built once, at booking time, from the same rules
    `applicable_refund_percentage` evaluates live — these tests check that
    summing the stored schedule up to a date reproduces exactly what the old
    on-the-fly calculation used to say was non-refundable as of that date.
    """

    def test_fully_refundable_zone_is_zero(self):
        rules = [CancellationRule(days_before_checkin=30, refund_percentage=1.0)]
        b = booking(rules, date(2026, 9, 1), price=1000.0)
        schedule = build_charge_schedule(b)
        assert scheduled_amount_due(schedule, date(2026, 8, 1)) == 0.0

    def test_partial_fee_zone(self):
        rules = [
            CancellationRule(days_before_checkin=30, refund_percentage=1.0),
            CancellationRule(days_before_checkin=7, refund_percentage=0.5),
        ]
        b = booking(rules, date(2026, 8, 20), price=1000.0)
        schedule = build_charge_schedule(b)
        assert scheduled_amount_due(schedule, date(2026, 8, 10)) == 500.0
        # Nothing further is due until the second threshold (checkin - 7 + 1)
        # kicks in.
        assert scheduled_amount_due(schedule, date(2026, 8, 13)) == 500.0
        assert scheduled_amount_due(schedule, date(2026, 8, 14)) == 1000.0

    def test_fully_non_refundable_zone_equals_total(self):
        rules = [CancellationRule(days_before_checkin=7, refund_percentage=1.0)]
        b = booking(rules, date(2026, 8, 5), price=1000.0)
        schedule = build_charge_schedule(b)
        assert scheduled_amount_due(schedule, date(2026, 8, 4)) == 1000.0

    def test_flat_fee_is_due_immediately_at_booking_time(self):
        # A rule pinned at 0 days-before-checkin applies for any actual
        # days-before-checkin, so its amount is due from booking day one
        # rather than waiting for any calendar milestone.
        rules = [CancellationRule(days_before_checkin=0, refund_percentage=0.5)]
        b = booking(rules, date(2026, 9, 1), price=1000.0, booking_date=date(2026, 8, 1))
        schedule = build_charge_schedule(b)
        assert scheduled_amount_due(schedule, date(2026, 8, 1)) == 500.0

    def test_no_rules_is_fully_due_immediately(self):
        b = booking([], date(2026, 9, 1), price=1000.0, booking_date=date(2026, 8, 1))
        schedule = build_charge_schedule(b)
        assert scheduled_amount_due(schedule, date(2026, 8, 1)) == 1000.0


class TestOutstandingAmount:
    def test_subtracts_what_is_already_charged(self):
        rules = [CancellationRule(days_before_checkin=0, refund_percentage=0.5)]
        b = booking(rules, date(2026, 9, 1), price=1000.0, booking_date=date(2026, 8, 1))
        b.charge_schedule = build_charge_schedule(b)
        b.amount_charged = 200.0
        assert outstanding_amount(b, date(2026, 8, 1)) == 300.0

    def test_zero_once_fully_covered(self):
        rules = [CancellationRule(days_before_checkin=0, refund_percentage=0.5)]
        b = booking(rules, date(2026, 9, 1), price=1000.0, booking_date=date(2026, 8, 1))
        b.charge_schedule = build_charge_schedule(b)
        b.amount_charged = 500.0
        assert outstanding_amount(b, date(2026, 8, 1)) == 0.0


class TestUpcomingCharges:
    def test_excludes_entries_already_due(self):
        rules = [
            CancellationRule(days_before_checkin=30, refund_percentage=1.0),
            CancellationRule(days_before_checkin=7, refund_percentage=0.5),
        ]
        b = booking(rules, date(2026, 8, 20), price=1000.0)
        b.charge_schedule = build_charge_schedule(b)

        upcoming = upcoming_charges(b, date(2026, 8, 10))

        assert [entry.charge_date for entry in upcoming] == [date(2026, 8, 14)]
        assert upcoming[0].amount == 500.0

    def test_empty_once_every_entry_is_due(self):
        rules = [CancellationRule(days_before_checkin=0, refund_percentage=0.5)]
        b = booking(rules, date(2026, 9, 1), price=1000.0, booking_date=date(2026, 8, 1))
        b.charge_schedule = build_charge_schedule(b)

        assert upcoming_charges(b, date(2026, 9, 1)) == []

    def test_sorted_by_charge_date(self):
        rules = [
            CancellationRule(days_before_checkin=30, refund_percentage=1.0),
            CancellationRule(days_before_checkin=7, refund_percentage=0.5),
        ]
        b = booking(rules, date(2026, 8, 20), price=1000.0, booking_date=date(2026, 7, 1))
        b.charge_schedule = build_charge_schedule(b)

        upcoming = upcoming_charges(b, date(2026, 6, 1))

        assert [entry.charge_date for entry in upcoming] == sorted(entry.charge_date for entry in upcoming)


class TestSyncChargeScheduleStatus:
    def test_marks_entries_done_up_to_amount_charged(self):
        rules = [
            CancellationRule(days_before_checkin=30, refund_percentage=1.0),
            CancellationRule(days_before_checkin=7, refund_percentage=0.5),
        ]
        b = booking(rules, date(2026, 8, 20), price=1000.0)
        b.charge_schedule = build_charge_schedule(b)
        b.amount_charged = 500.0

        sync_charge_schedule_status(b)

        statuses = [entry.status for entry in sorted(b.charge_schedule, key=lambda e: e.charge_date)]
        assert statuses == ["done", "pending"]

    def test_refund_reverts_status_to_pending(self):
        rules = [CancellationRule(days_before_checkin=0, refund_percentage=0.5)]
        b = booking(rules, date(2026, 9, 1), price=1000.0, booking_date=date(2026, 8, 1))
        b.charge_schedule = build_charge_schedule(b)
        b.amount_charged = 500.0
        sync_charge_schedule_status(b)
        assert b.charge_schedule[0].status == "done"

        b.amount_charged = 0.0
        sync_charge_schedule_status(b)
        assert b.charge_schedule[0].status == "pending"


class TestScheduleFollowsTheDiscountedTotal:
    """Promotions change `price`, and `price` is what the schedule is built
    from — the struck-through `regular_price` must never reach a charge."""

    def test_schedule_sums_to_the_discounted_total(self):
        rules = [
            CancellationRule(days_before_checkin=30, refund_percentage=1.0),
            CancellationRule(days_before_checkin=7, refund_percentage=0.5),
        ]
        b = booking(rules, date(2026, 8, 20), price=800.0, regular_price=1000.0)
        schedule = build_charge_schedule(b)
        assert sum(entry.amount for entry in schedule) == 800.0
        # ... and it is due on exactly the same dates as before, at the
        # same proportions of the (now discounted) total.
        assert scheduled_amount_due(schedule, date(2026, 8, 10)) == 400.0
        assert scheduled_amount_due(schedule, date(2026, 8, 14)) == 800.0

    def test_outstanding_amount_ignores_the_regular_price(self):
        rules = [CancellationRule(days_before_checkin=0, refund_percentage=0.0)]
        b = booking(rules, date(2026, 9, 1), price=800.0, regular_price=1000.0, booking_date=date(2026, 8, 1))
        b.charge_schedule = build_charge_schedule(b)
        b.amount_charged = 800.0
        assert outstanding_amount(b, date(2026, 8, 1)) == 0.0
