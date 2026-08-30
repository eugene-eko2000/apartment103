"""find_overlapping_ranges: what clashes with a candidate booking, and
discard_overlapping_pending_bookings: what happens to the guests it beat.

Guards the boundary condition the whole calendar depends on — end_date is an
exclusive checkout day, so checking out on the morning another stay checks in
is *not* an overlap — and pins the behaviour of the MongoDB $elemMatch query
that replaced the original in-Python scan.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.booking import (
    Booking,
    BookingCancellationPolicy,
    BookingCharge,
    BookingDateRange,
    nights_of_ranges,
)
from app.models.cancellation_policy import CancellationRule
from app.models.closure import Closure
from app.services.availability import (
    DATES_TAKEN_MESSAGE,
    discard_overlapping_pending_bookings,
    expire_pending_bookings,
    find_overlapping_ranges,
)

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

    async def test_a_pending_booking_blocks(self, client, guest, other_guest):
        """A guest in checkout holds their nights — that is what makes two
        simultaneous checkouts for the same dates impossible."""
        await _booking(guest, ("2026-09-01", "2026-09-05"), status="Pending")
        candidate = await _booking(other_guest, ("2026-09-02", "2026-09-04"), status="Pending")

        overlapping = await find_overlapping_ranges(candidate)

        assert len(overlapping) == 1
        assert overlapping[0].begin_date == date(2026, 9, 1)

    async def test_an_expired_pending_booking_blocks_nothing(self, client, guest, other_guest):
        """A checkout that ran out of time is swept away by the lookup
        itself, so its dates read as free."""
        stale = await _booking(guest, ("2026-09-01", "2026-09-05"), status="Pending")
        await stale.set({Booking.pending_expires_at: datetime.now(timezone.utc) - timedelta(minutes=1)})
        candidate = await _booking(other_guest, ("2026-09-02", "2026-09-04"), status="Pending")

        assert await find_overlapping_ranges(candidate) == []
        assert await Booking.get(stale.id) is None

    async def test_ignores_cancelled_bookings(self, client, guest, other_guest):
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


class TestClosuresBlockBookings:
    """Dates taken on Airbnb/Booking.com (synced in as closures) or blocked
    by the host are as unavailable as another site booking — the public
    calendar greys them out, but the page may predate the last sync pass."""

    async def _closure(self, begin: str, end: str, **kwargs) -> Closure:
        closure = Closure(
            platform="Airbnb",
            begin_date=date.fromisoformat(begin),
            end_date=date.fromisoformat(end),
            **kwargs,
        )
        await closure.insert()
        return closure

    async def test_detects_an_overlapping_closure(self, client, guest):
        await self._closure("2026-09-01", "2026-09-05")
        candidate = await _booking(guest, ("2026-09-03", "2026-09-08"), status="Pending")

        overlapping = await find_overlapping_ranges(candidate)

        assert len(overlapping) == 1
        assert overlapping[0].begin_date == date(2026, 9, 1)
        assert overlapping[0].end_date == date(2026, 9, 5)

    async def test_detects_an_imported_closure(self, client, guest, external_calendar):
        await self._closure(
            "2026-09-01",
            "2026-09-05",
            external_calendar_id=external_calendar.id,
            external_uid="a@airbnb.com",
        )
        candidate = await _booking(guest, ("2026-09-02", "2026-09-04"), status="Pending")

        assert len(await find_overlapping_ranges(candidate)) == 1

    async def test_closure_checkout_day_may_be_a_checkin(self, client, guest):
        """Same exclusive-end convention as bookings."""
        await self._closure("2026-09-01", "2026-09-05")
        candidate = await _booking(guest, ("2026-09-05", "2026-09-09"), status="Pending")

        assert await find_overlapping_ranges(candidate) == []

    async def test_ignores_closures_on_other_dates(self, client, guest):
        await self._closure("2026-09-01", "2026-09-05")
        candidate = await _booking(guest, ("2026-10-01", "2026-10-05"), status="Pending")

        assert await find_overlapping_ranges(candidate) == []


class TestDiscardOverlappingPendingBookings:
    """What the winner's activation does to everyone still mid-checkout on
    the same nights.

    They are removed, not parked as cancellations: nothing was ever charged
    against a Pending booking, and a stay the guest was never granted is not
    a cancellation they should keep seeing in their bookings (or the host in
    the admin list).
    """

    async def test_removes_an_overlapping_pending_booking(self, client, guest, other_guest):
        winner = await _booking(guest, ("2026-09-01", "2026-09-05"))
        loser = await _booking(other_guest, ("2026-09-03", "2026-09-07"), status="Pending")

        assert await discard_overlapping_pending_bookings(winner) == 1
        assert await Booking.get(loser.id) is None

    async def test_leaves_pending_bookings_on_other_dates_alone(self, client, guest, other_guest):
        winner = await _booking(guest, ("2026-09-01", "2026-09-05"))
        untouched = await _booking(other_guest, ("2026-09-05", "2026-09-09"), status="Pending")

        assert await discard_overlapping_pending_bookings(winner) == 0
        assert await Booking.get(untouched.id) is not None

    async def test_never_touches_the_winner_itself(self, client, guest):
        winner = await _booking(guest, ("2026-09-01", "2026-09-05"))

        assert await discard_overlapping_pending_bookings(winner) == 0
        assert await Booking.get(winner.id) is not None

    async def test_keeps_a_pending_booking_that_somehow_carries_charges(self, client, guest, other_guest):
        # The invariant is that a Pending booking has no charges — the
        # opening charge is what activates one. If it is ever broken, money
        # history must outlive the race, so such a booking is cancelled the
        # old way rather than deleted.
        winner = await _booking(guest, ("2026-09-01", "2026-09-05"))
        loser = await _booking(other_guest, ("2026-09-03", "2026-09-07"), status="Pending")
        loser.charges = [
            BookingCharge(
                stripe_payment_intent_id="pi_stray",
                amount=100,
                currency="CHF",
                reason="initial_charge",
                status="succeeded",
            )
        ]
        await loser.save()

        assert await discard_overlapping_pending_bookings(winner) == 1
        kept = await Booking.get(loser.id)
        assert kept is not None
        assert kept.status == "Cancelled"
        assert kept.last_payment_error == DATES_TAKEN_MESSAGE
        assert kept.booked_nights == []


class TestExpirePendingBookings:
    """The temporary half of the temporary block: a checkout nobody finished
    gives the dates back on its own."""

    async def _pending(self, guest, *pairs: tuple[str, str], expires_in_minutes: float) -> Booking:
        booking = await _booking(guest, *pairs, status="Pending")
        await booking.set(
            {
                Booking.pending_expires_at: datetime.now(timezone.utc)
                + timedelta(minutes=expires_in_minutes)
            }
        )
        return booking

    async def test_removes_a_lapsed_pending_booking(self, client, guest):
        lapsed = await self._pending(guest, ("2026-09-01", "2026-09-05"), expires_in_minutes=-1)

        assert await expire_pending_bookings() == 1
        assert await Booking.get(lapsed.id) is None

    async def test_keeps_a_pending_booking_still_within_its_window(self, client, guest):
        live = await self._pending(guest, ("2026-09-01", "2026-09-05"), expires_in_minutes=5)

        assert await expire_pending_bookings() == 0
        assert await Booking.get(live.id) is not None

    async def test_never_touches_active_or_cancelled_bookings(self, client, guest, other_guest):
        # Neither carries a deadline, so neither can lapse — asserted rather
        # than assumed, since an Active booking losing its dates to the sweep
        # would be a booking silently disappearing after being paid for.
        active = await _booking(guest, ("2026-09-01", "2026-09-05"))
        cancelled = await _booking(other_guest, ("2026-10-01", "2026-10-05"), status="Cancelled")

        assert await expire_pending_bookings() == 0
        assert await Booking.get(active.id) is not None
        assert await Booking.get(cancelled.id) is not None

    async def test_keeps_a_lapsed_booking_that_carries_charges(self, client, guest):
        # A payment confirmed just before the deadline can still be in
        # flight. Money already taken must never have its booking swept out
        # from under it — the payment paths resolve that one.
        paid = await self._pending(guest, ("2026-09-01", "2026-09-05"), expires_in_minutes=-1)
        paid.charges = [
            BookingCharge(
                stripe_payment_intent_id="pi_in_flight",
                amount=100,
                currency="CHF",
                reason="initial_charge",
                status="succeeded",
            )
        ]
        await paid.save()

        assert await expire_pending_bookings() == 0
        assert await Booking.get(paid.id) is not None

    async def test_releases_the_nights_for_a_new_booking(self, client, guest, other_guest):
        """The point of the sweep: the dates become bookable again."""
        lapsed = await self._pending(guest, ("2026-09-01", "2026-09-05"), expires_in_minutes=-1)
        await lapsed.set({Booking.booked_nights: nights_of_ranges(lapsed.date_ranges)})
        candidate = await _booking(other_guest, ("2026-09-01", "2026-09-05"), status="Pending")

        assert await find_overlapping_ranges(candidate) == []
