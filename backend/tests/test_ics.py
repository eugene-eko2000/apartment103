"""Reading and writing the .ics feeds both sync directions ride on.

The fixtures under tests/fixtures/ics mirror what Airbnb and Booking.com
actually export (folded DESCRIPTION lines, their own PRODIDs, their own
SUMMARY wording), since the point of these tests is interop with those two
feeds rather than with a calendar we wrote ourselves.
"""

from datetime import date, datetime, timezone
from pathlib import Path

from icalendar import Calendar

from app.services.ics import IcsEvent, build_calendar, parse_calendar

FIXTURES = Path(__file__).parent / "fixtures" / "ics"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _lines(raw: bytes) -> list[str]:
    return raw.decode().splitlines()


class TestParseCalendar:
    def test_reads_an_airbnb_export(self):
        events = parse_calendar(_fixture("airbnb_export.ics"))

        assert [(event.begin_date, event.end_date) for event in events] == [
            (date(2026, 8, 1), date(2026, 8, 5)),
            (date(2026, 8, 15), date(2026, 8, 20)),
        ]
        assert events[0].uid == "1a2b3c4d5e6f7890abcdef1234567890@airbnb.com"
        assert events[1].summary == "Airbnb (Not available)"

    def test_reads_a_booking_com_export(self):
        events = parse_calendar(_fixture("booking_com_export.ics"))

        assert len(events) == 1
        assert events[0].begin_date == date(2026, 9, 10)
        # DTEND stays exclusive: a 20260913 checkout must not block the 13th.
        assert events[0].end_date == date(2026, 9, 13)
        assert events[0].summary == "CLOSED - Not available"

    def test_skips_cancelled_events(self):
        raw = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:gone@example.com
DTSTART;VALUE=DATE:20260901
DTEND;VALUE=DATE:20260905
STATUS:CANCELLED
END:VEVENT
END:VCALENDAR
"""
        assert parse_calendar(raw) == []

    def test_all_day_event_without_dtend_covers_one_night(self):
        raw = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:oneday@example.com
DTSTART;VALUE=DATE:20260901
END:VEVENT
END:VCALENDAR
"""
        assert parse_calendar(raw) == [
            IcsEvent(uid="oneday@example.com", begin_date=date(2026, 9, 1), end_date=date(2026, 9, 2))
        ]

    def test_duration_stands_in_for_a_missing_dtend(self):
        raw = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:dur@example.com
DTSTART;VALUE=DATE:20260901
DURATION:P3D
END:VEVENT
END:VCALENDAR
"""
        assert parse_calendar(raw)[0].end_date == date(2026, 9, 4)

    def test_timed_events_collapse_to_their_calendar_days(self):
        """Google/Outlook export timed VEVENTs; the block is still a range of
        nights."""
        raw = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:timed@example.com
DTSTART:20260901T140000Z
DTEND:20260905T100000Z
END:VEVENT
END:VCALENDAR
"""
        event = parse_calendar(raw)[0]
        assert (event.begin_date, event.end_date) == (date(2026, 9, 1), date(2026, 9, 5))

    def test_zero_length_event_becomes_a_single_night(self):
        raw = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:empty@example.com
DTSTART;VALUE=DATE:20260901
DTEND;VALUE=DATE:20260901
END:VEVENT
END:VCALENDAR
"""
        assert parse_calendar(raw)[0].end_date == date(2026, 9, 2)

    def test_event_without_uid_gets_a_date_derived_one(self):
        raw = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
DTSTART;VALUE=DATE:20260901
DTEND;VALUE=DATE:20260905
END:VEVENT
END:VCALENDAR
"""
        # Stable across polls, which is what the (calendar, uid) upsert key
        # needs — a random one would re-create the closure on every pass.
        assert parse_calendar(raw)[0].uid == "2026-09-01/2026-09-05"

    def test_keeps_only_the_first_event_of_a_repeated_uid(self):
        raw = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:dupe@example.com
DTSTART;VALUE=DATE:20260901
DTEND;VALUE=DATE:20260905
END:VEVENT
BEGIN:VEVENT
UID:dupe@example.com
DTSTART;VALUE=DATE:20261001
DTEND;VALUE=DATE:20261005
END:VEVENT
END:VCALENDAR
"""
        events = parse_calendar(raw)
        assert len(events) == 1
        assert events[0].begin_date == date(2026, 9, 1)

    def test_one_broken_event_does_not_lose_the_rest(self):
        raw = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:broken@example.com
SUMMARY:No dates at all
END:VEVENT
BEGIN:VEVENT
UID:fine@example.com
DTSTART;VALUE=DATE:20260901
DTEND;VALUE=DATE:20260905
END:VEVENT
END:VCALENDAR
"""
        assert [event.uid for event in parse_calendar(raw)] == ["fine@example.com"]


class TestBuildCalendar:
    def test_emits_all_day_events_with_an_exclusive_end(self):
        raw = build_calendar(
            [IcsEvent(uid="booking-1@apartment103.example", begin_date=date(2026, 8, 1), end_date=date(2026, 8, 5))],
            now=datetime(2026, 7, 13, tzinfo=timezone.utc),
        )

        lines = _lines(raw)
        # VALUE=DATE, not a date-time: Airbnb and Booking.com read all-day
        # events, and a timed DTSTART can be ignored outright.
        assert "DTSTART;VALUE=DATE:20260801" in lines
        assert "DTEND;VALUE=DATE:20260805" in lines
        assert "SUMMARY:Reserved" in lines
        assert "TRANSP:OPAQUE" in lines
        assert "UID:booking-1@apartment103.example" in lines
        assert "DTSTAMP:20260713T000000Z" in lines

    def test_carries_no_guest_or_price_details(self):
        raw = build_calendar(
            [IcsEvent(uid="booking-1@apartment103.example", begin_date=date(2026, 8, 1), end_date=date(2026, 8, 5))]
        ).decode()

        assert "DESCRIPTION" not in raw
        assert "ATTENDEE" not in raw

    def test_round_trips_through_the_parser(self):
        events = [
            IcsEvent(uid="a@apartment103.example", begin_date=date(2026, 8, 1), end_date=date(2026, 8, 5)),
            IcsEvent(uid="b@apartment103.example", begin_date=date(2026, 9, 1), end_date=date(2026, 9, 3)),
        ]

        assert parse_calendar(build_calendar(events)) == events

    def test_is_a_valid_vcalendar_for_a_third_party_reader(self):
        raw = build_calendar([])

        calendar = Calendar.from_ical(raw)
        assert calendar.get("version") == "2.0"
        assert "apartment103" in str(calendar.get("prodid"))
