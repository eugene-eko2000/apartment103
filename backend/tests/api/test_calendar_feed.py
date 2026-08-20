"""Outbound feed: GET /calendar/{token}.ics.

This is what Airbnb and Booking.com poll, so the tests are about what a
strict, unattended consumer sees — that the token really gates it, that the
dates land on the right days, and above all that the feed served to one
platform never contains that platform's own blocks (which would echo back
and forth between the two propagation delays).
"""

from datetime import date

import pytest
from icalendar import Calendar

from app.core.config import settings
from app.models.booking import Booking, BookingCancellationPolicy, BookingDateRange
from app.models.cancellation_policy import CancellationRule
from app.models.closure import Closure

pytestmark = pytest.mark.anyio


async def _booking(guest, begin: str, end: str, status: str = "Active") -> Booking:
    booking = Booking(
        guest=guest,
        date_ranges=[
            BookingDateRange(begin_date=date.fromisoformat(begin), end_date=date.fromisoformat(end), price=100)
        ],
        cancellation_policy=BookingCancellationPolicy(
            name="Flexible", rules=[CancellationRule(days_before_checkin=1, refund_percentage=1.0)]
        ),
        status=status,
    )
    await booking.insert()
    return booking


def _ranges(body: bytes) -> set[tuple[date, date]]:
    calendar = Calendar.from_ical(body)
    return {(event.get("dtstart").dt, event.get("dtend").dt) for event in calendar.walk("VEVENT")}


class TestExportFeed:
    async def test_serves_an_ics_document(self, client, external_calendar, guest):
        await _booking(guest, "2026-09-01", "2026-09-05")

        response = await client.get(f"/calendar/{external_calendar.export_token}.ics")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/calendar")
        assert response.content.startswith(b"BEGIN:VCALENDAR")
        assert _ranges(response.content) == {(date(2026, 9, 1), date(2026, 9, 5))}

    async def test_needs_no_authentication(self, client, external_calendar):
        """ICS consumers can't send an Authorization header — the token is
        the credential."""
        assert (await client.get(f"/calendar/{external_calendar.export_token}.ics")).status_code == 200

    async def test_unknown_token_is_404(self, client, external_calendar):
        assert (await client.get("/calendar/not-a-real-token.ics")).status_code == 404

    async def test_excludes_pending_and_cancelled_bookings(self, client, external_calendar, guest):
        await _booking(guest, "2026-09-01", "2026-09-05", status="Pending")
        await _booking(guest, "2026-10-01", "2026-10-05", status="Cancelled")

        response = await client.get(f"/calendar/{external_calendar.export_token}.ics")

        assert _ranges(response.content) == set()

    async def test_includes_manual_closures(self, client, external_calendar, closure):
        response = await client.get(f"/calendar/{external_calendar.export_token}.ics")

        assert _ranges(response.content) == {(closure.begin_date, closure.end_date)}

    async def test_omits_the_blocks_that_came_from_this_calendar(self, client, external_calendar):
        """Otherwise Airbnb re-imports its own reservations, and a
        cancellation can bounce between the two propagation delays."""
        await Closure(
            platform="Airbnb",
            begin_date=date(2026, 9, 1),
            end_date=date(2026, 9, 5),
            external_calendar_id=external_calendar.id,
            external_uid="a@airbnb.com",
        ).insert()

        response = await client.get(f"/calendar/{external_calendar.export_token}.ics")

        assert _ranges(response.content) == set()

    async def test_passes_on_the_other_calendars_blocks(
        self, client, external_calendar, other_external_calendar
    ):
        """A Booking.com reservation has to reach Airbnb, and our feed is the
        only thing the host pasted there."""
        await Closure(
            platform="Booking.com",
            begin_date=date(2026, 10, 1),
            end_date=date(2026, 10, 5),
            external_calendar_id=other_external_calendar.id,
            external_uid="b@booking.com",
        ).insert()

        response = await client.get(f"/calendar/{external_calendar.export_token}.ics")

        assert _ranges(response.content) == {(date(2026, 10, 1), date(2026, 10, 5))}

    async def test_a_multi_range_booking_exports_one_event_per_range(self, client, external_calendar, guest):
        booking = Booking(
            guest=guest,
            date_ranges=[
                BookingDateRange(begin_date=date(2026, 9, 1), end_date=date(2026, 9, 5), price=100),
                BookingDateRange(begin_date=date(2026, 9, 5), end_date=date(2026, 9, 9), price=120),
            ],
            cancellation_policy=BookingCancellationPolicy(
                name="Flexible", rules=[CancellationRule(days_before_checkin=1, refund_percentage=1.0)]
            ),
            status="Active",
        )
        await booking.insert()

        response = await client.get(f"/calendar/{external_calendar.export_token}.ics")

        calendar = Calendar.from_ical(response.content)
        uids = [str(event.get("uid")) for event in calendar.walk("VEVENT")]
        # Distinct UIDs, or the consumer keeps only one of the two ranges.
        assert len(uids) == len(set(uids)) == 2

    async def test_carries_no_guest_details(self, client, external_calendar, guest):
        await _booking(guest, "2026-09-01", "2026-09-05")

        body = (await client.get(f"/calendar/{external_calendar.export_token}.ics")).content.decode()

        assert guest.family_name not in body
        assert guest.email not in body
        assert "100" not in body
        assert "SUMMARY:Reserved" in body


class TestSiteWideToken:
    @pytest.fixture(autouse=True)
    def site_token(self):
        settings.calendar_export_token = "site-wide-token"
        yield "site-wide-token"
        settings.calendar_export_token = None

    async def test_serves_everything_including_imported_blocks(
        self, client, external_calendar, site_token
    ):
        await Closure(
            platform="Airbnb",
            begin_date=date(2026, 9, 1),
            end_date=date(2026, 9, 5),
            external_calendar_id=external_calendar.id,
            external_uid="a@airbnb.com",
        ).insert()

        response = await client.get(f"/calendar/{site_token}.ics")

        assert response.status_code == 200
        assert _ranges(response.content) == {(date(2026, 9, 1), date(2026, 9, 5))}

    async def test_is_disabled_when_unset(self, client):
        settings.calendar_export_token = None

        assert (await client.get("/calendar/.ics")).status_code == 404
