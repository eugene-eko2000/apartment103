"""find_overlapping_ranges: which Active bookings clash with a candidate.

Guards the boundary condition the whole calendar depends on — end_date is an
exclusive checkout day, so checking out on the morning another stay checks in
is *not* an overlap — and pins the behaviour of the MongoDB $elemMatch query
that replaced the original in-Python scan.
"""

from datetime import date

import pytest

from app.models.booking import Booking, BookingCancellationPolicy, BookingDateRange
from app.models.cancellation_policy import CancellationRule
from app.services.availability import find_overlapping_ranges

pytestmark = pytest.mark.anyio


def _ranges(*pairs: tuple[str, str]) -> list[BookingDateRange]:
    return [
        BookingDateRange(begin_date=date.fromisoformat(begin), end_date=date.fromisoformat(end), price=100)
        for begin, end in pairs
    ]


async def _booking(guest, *pairs: tuple[str, str], status: str = "Active") -> Booking:
    booking = Booking(
        guest=guest,
        date_ranges=_ranges(*pairs),
        cancellation_policy=BookingCancellationPolicy(
            name="Flexible", rules=[CancellationRule(days_before_checkin=1, refund_percentage=1.0)]
        ),
        status=status,
    )
    await booking.insert()
    return booking


class TestFindOverlappingRanges:
    async def test_no_overlap_for_separate_dates(self, client, guest, other_guest):
        await _booking(guest, ("2026-09-01", "2026-09-05"))
        candidate = await _booking(other_guest, ("2026-09-10", "2026-09-14"), status="Pending")

        assert await find_overlapping_ranges(candidate) == []

    async def test_checkout_day_may_be_another_stays_checkin(self, client, guest, other_guest):
        """The exclusive-end-date convention: back-to-back stays don't clash."""
        await _booking(guest, ("2026-09-01", "2026-09-05"))
        candidate = await _booking(other_guest, ("2026-09-05", "2026-09-09"), status="Pending")

        assert await find_overlapping_ranges(candidate) == []

    async def test_checkin_day_may_be_another_stays_checkout(self, client, guest, other_guest):
        await _booking(guest, ("2026-09-05", "2026-09-09"))
        candidate = await _booking(other_guest, ("2026-09-01", "2026-09-05"), status="Pending")

        assert await find_overlapping_ranges(candidate) == []

    @pytest.mark.parametrize(
        "candidate_range",
        [
            ("2026-09-02", "2026-09-04"),  # fully inside
            ("2026-08-28", "2026-09-20"),  # fully containing
            ("2026-08-30", "2026-09-03"),  # straddles the start
            ("2026-09-03", "2026-09-08"),  # straddles the end
            ("2026-09-04", "2026-09-06"),  # one shared night
        ],
    )
    async def test_detects_every_kind_of_overlap(self, client, guest, other_guest, candidate_range):
        await _booking(guest, ("2026-09-01", "2026-09-05"))
        candidate = await _booking(other_guest, candidate_range, status="Pending")

        overlapping = await find_overlapping_ranges(candidate)

        assert len(overlapping) == 1
        assert overlapping[0].begin_date == date(2026, 9, 1)
        assert overlapping[0].end_date == date(2026, 9, 5)

    async def test_ignores_non_active_bookings(self, client, guest, other_guest):
        """Pending bookings deliberately don't block the calendar."""
        await _booking(guest, ("2026-09-01", "2026-09-05"), status="Pending")
        await _booking(guest, ("2026-09-01", "2026-09-05"), status="Cancelled")
        candidate = await _booking(other_guest, ("2026-09-02", "2026-09-04"), status="Pending")

        assert await find_overlapping_ranges(candidate) == []

    async def test_ignores_the_booking_itself(self, client, guest):
        candidate = await _booking(guest, ("2026-09-01", "2026-09-05"))

        assert await find_overlapping_ranges(candidate) == []

    async def test_matches_any_of_several_candidate_ranges(self, client, guest, other_guest):
        await _booking(guest, ("2026-10-10", "2026-10-14"))
        candidate = await _booking(
            other_guest, ("2026-09-01", "2026-09-05"), ("2026-10-12", "2026-10-16"), status="Pending"
        )

        overlapping = await find_overlapping_ranges(candidate)

        assert len(overlapping) == 1
        assert overlapping[0].begin_date == date(2026, 10, 10)

    async def test_returns_empty_for_a_booking_with_no_dates(self, client, guest, other_guest):
        await _booking(guest, ("2026-09-01", "2026-09-05"))
        candidate = await _booking(other_guest, status="Pending")

        assert await find_overlapping_ranges(candidate) == []
