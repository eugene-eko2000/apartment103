"""Inbound sync: an external .ics feed becoming Closure documents.

The reconciliation is what matters here — the same feed polled twice must
not duplicate anything, a range that moved must move, a VEVENT that
disappeared must take its closure with it, and a feed that fails to load
must change nothing at all.
"""

from datetime import date, datetime, timezone

import httpx
import pytest

from app.models.closure import Closure
from app.models.external_calendar import ExternalCalendar
from app.services import calendar_sync
from app.services.calendar_sync import sync_all_external_calendars, sync_external_calendar

pytestmark = pytest.mark.anyio


def _feed(*events: tuple[str, str, str]) -> bytes:
    body = "".join(
        f"BEGIN:VEVENT\nUID:{uid}\nDTSTART;VALUE=DATE:{begin}\nDTEND;VALUE=DATE:{end}\nSUMMARY:Reserved\nEND:VEVENT\n"
        for uid, begin, end in events
    )
    return f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Test//EN\n{body}END:VCALENDAR\n".encode()


@pytest.fixture
def feed(monkeypatch):
    """Serve a canned .ics body (or raise) instead of hitting the network."""

    responses: dict[str, bytes | Exception] = {}

    async def _fake_fetch(url: str) -> bytes:
        value = responses[url]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(calendar_sync, "fetch_calendar_feed", _fake_fetch)
    return responses


class TestSyncExternalCalendar:
    async def test_imports_events_as_closures(self, client, external_calendar, feed):
        feed[external_calendar.url] = _feed(("a@airbnb.com", "20260901", "20260905"))

        result = await sync_external_calendar(external_calendar)

        assert (result.status, result.created, result.updated, result.deleted) == ("ok", 1, 0, 0)
        closure = await Closure.find_one(Closure.external_uid == "a@airbnb.com")
        assert closure.begin_date == date(2026, 9, 1)
        assert closure.end_date == date(2026, 9, 5)
        # The calendar's name is what the closure is labelled with, so the
        # existing closures list/admin UI shows where a block came from.
        assert closure.platform == "Airbnb"
        assert closure.external_calendar_id == external_calendar.id

    async def test_re_syncing_the_same_feed_changes_nothing(self, client, external_calendar, feed):
        feed[external_calendar.url] = _feed(("a@airbnb.com", "20260901", "20260905"))
        await sync_external_calendar(external_calendar)

        result = await sync_external_calendar(external_calendar)

        assert (result.created, result.updated, result.deleted) == (0, 1, 0)
        assert await Closure.find_all().count() == 1

    async def test_moved_dates_update_the_existing_closure(self, client, external_calendar, feed):
        feed[external_calendar.url] = _feed(("a@airbnb.com", "20260901", "20260905"))
        await sync_external_calendar(external_calendar)

        feed[external_calendar.url] = _feed(("a@airbnb.com", "20260902", "20260907"))
        await sync_external_calendar(external_calendar)

        closures = await Closure.find_all().to_list()
        assert len(closures) == 1
        assert (closures[0].begin_date, closures[0].end_date) == (date(2026, 9, 2), date(2026, 9, 7))

    async def test_disappeared_event_removes_its_closure(self, client, external_calendar, feed):
        """The reservation was cancelled on the other platform."""
        feed[external_calendar.url] = _feed(
            ("a@airbnb.com", "20260901", "20260905"), ("b@airbnb.com", "20261001", "20261005")
        )
        await sync_external_calendar(external_calendar)

        feed[external_calendar.url] = _feed(("a@airbnb.com", "20260901", "20260905"))
        result = await sync_external_calendar(external_calendar)

        assert result.deleted == 1
        assert [closure.external_uid for closure in await Closure.find_all().to_list()] == ["a@airbnb.com"]

    async def test_leaves_manual_closures_alone(self, client, external_calendar, closure, feed):
        """`closure` is the hand-entered fixture: no external_calendar_id."""
        feed[external_calendar.url] = _feed(("a@airbnb.com", "20260901", "20260905"))

        await sync_external_calendar(external_calendar)

        manual = await Closure.get(closure.id)
        assert manual is not None
        assert manual.external_calendar_id is None

    async def test_leaves_another_calendars_closures_alone(
        self, client, external_calendar, other_external_calendar, feed
    ):
        feed[external_calendar.url] = _feed(("a@airbnb.com", "20260901", "20260905"))
        feed[other_external_calendar.url] = _feed(("b@booking.com", "20261001", "20261005"))
        await sync_all_external_calendars()

        # Airbnb's feed empties out; Booking.com's block must survive it.
        feed[external_calendar.url] = _feed()
        await sync_external_calendar(external_calendar)

        assert [closure.external_uid for closure in await Closure.find_all().to_list()] == ["b@booking.com"]

    async def test_records_success_on_the_calendar(self, client, external_calendar, feed):
        feed[external_calendar.url] = _feed(("a@airbnb.com", "20260901", "20260905"))

        await sync_external_calendar(external_calendar)

        stored = await ExternalCalendar.get(external_calendar.id)
        assert stored.last_sync_status == "ok"
        assert stored.last_sync_error is None
        assert stored.last_sync_block_count == 1
        assert stored.last_synced_at is not None

    async def test_a_failing_feed_is_recorded_and_keeps_existing_closures(
        self, client, external_calendar, feed
    ):
        """An unreachable feed must not read as "nothing is booked" — that
        would free up dates still taken on the other platform."""
        feed[external_calendar.url] = _feed(("a@airbnb.com", "20260901", "20260905"))
        await sync_external_calendar(external_calendar)

        feed[external_calendar.url] = httpx.ConnectError("boom")
        result = await sync_external_calendar(external_calendar)

        assert result.status == "error"
        assert "boom" in result.error
        assert await Closure.find_all().count() == 1
        stored = await ExternalCalendar.get(external_calendar.id)
        assert stored.last_sync_status == "error"
        # The count from the last *successful* pass is kept, so the admin
        # still sees what was there before the feed broke.
        assert stored.last_sync_block_count == 1

    async def test_a_non_calendar_response_is_an_error_not_an_empty_feed(
        self, client, external_calendar, feed
    ):
        feed[external_calendar.url] = b"<html>Sign in to continue</html>"

        result = await sync_external_calendar(external_calendar)

        assert result.status == "error"
        assert await Closure.find_all().count() == 0

    async def test_one_broken_calendar_does_not_stop_the_others(
        self, client, external_calendar, other_external_calendar, feed
    ):
        feed[external_calendar.url] = httpx.ConnectError("boom")
        feed[other_external_calendar.url] = _feed(("b@booking.com", "20261001", "20261005"))

        results = await sync_all_external_calendars()

        assert {result.status for result in results} == {"error", "ok"}
        assert await Closure.find_all().count() == 1


class TestFetchCalendarFeed:
    async def test_follows_redirects_and_returns_the_body(self, monkeypatch):
        """Both OTAs' export links redirect at least once before the .ics."""
        requested: dict = {}

        class _FakeClient:
            def __init__(self, **kwargs):
                requested["kwargs"] = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, url, headers=None):
                requested["url"] = url
                return httpx.Response(
                    200,
                    content=b"BEGIN:VCALENDAR\nEND:VCALENDAR\n",
                    request=httpx.Request("GET", url),
                )

        monkeypatch.setattr(calendar_sync.httpx, "AsyncClient", _FakeClient)

        body = await calendar_sync.fetch_calendar_feed("https://example.com/cal.ics")

        assert body.startswith(b"BEGIN:VCALENDAR")
        assert requested["url"] == "https://example.com/cal.ics"
        assert requested["kwargs"]["follow_redirects"] is True

    async def test_raises_on_an_error_status(self, monkeypatch):
        class _FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, url, headers=None):
                return httpx.Response(403, request=httpx.Request("GET", url))

        monkeypatch.setattr(calendar_sync.httpx, "AsyncClient", _FakeClient)

        with pytest.raises(httpx.HTTPStatusError):
            await calendar_sync.fetch_calendar_feed("https://example.com/cal.ics")


class TestLastSeenAt:
    async def test_is_stamped_on_import(self, client, external_calendar, feed):
        feed[external_calendar.url] = _feed(("a@airbnb.com", "20260901", "20260905"))
        # MongoDB stores datetimes at millisecond resolution, so compare
        # against a floor rather than the exact "now" taken here.
        before = datetime.now(timezone.utc).replace(microsecond=0)

        await sync_external_calendar(external_calendar)

        closure = await Closure.find_one(Closure.external_uid == "a@airbnb.com")
        assert closure.last_seen_at >= before
