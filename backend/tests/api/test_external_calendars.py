import pytest

from app.models.closure import Closure
from app.models.external_calendar import ExternalCalendar
from app.services import calendar_sync

pytestmark = pytest.mark.anyio


def _payload(**overrides):
    payload = {"name": "Airbnb", "url": "https://www.airbnb.com/calendar/ical/12345.ics?s=secret"}
    payload.update(overrides)
    return payload


class TestCreateExternalCalendar:
    async def test_creates_a_calendar_with_an_export_token(self, client, admin_headers):
        response = await client.post("/external-calendars", json=_payload(), headers=admin_headers)

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Airbnb"
        assert body["url"] == "https://www.airbnb.com/calendar/ical/12345.ics?s=secret"
        # Generated server-side: it's the credential for this calendar's
        # outbound feed, so it is never taken from the request.
        assert body["export_token"]
        assert body["last_sync_status"] is None

    async def test_export_tokens_are_unique_per_calendar(self, client, admin_headers):
        first = await client.post("/external-calendars", json=_payload(), headers=admin_headers)
        second = await client.post(
            "/external-calendars", json=_payload(name="Booking.com"), headers=admin_headers
        )

        assert first.json()["export_token"] != second.json()["export_token"]

    async def test_rewrites_a_webcal_url(self, client, admin_headers):
        response = await client.post(
            "/external-calendars", json=_payload(url="webcal://example.com/cal.ics"), headers=admin_headers
        )

        assert response.status_code == 201
        assert response.json()["url"] == "https://example.com/cal.ics"

    async def test_rejects_a_url_that_is_not_a_link(self, client, admin_headers):
        response = await client.post(
            "/external-calendars", json=_payload(url="not-a-url"), headers=admin_headers
        )
        assert response.status_code == 422

    async def test_rejects_a_blank_name(self, client, admin_headers):
        response = await client.post("/external-calendars", json=_payload(name="   "), headers=admin_headers)
        assert response.status_code == 422

    async def test_requires_admin(self, client, guest_headers):
        response = await client.post("/external-calendars", json=_payload(), headers=guest_headers)
        assert response.status_code == 403

    async def test_requires_authentication(self, client):
        response = await client.post("/external-calendars", json=_payload())
        assert response.status_code == 401


class TestListExternalCalendars:
    async def test_lists_calendars(self, client, admin_headers, external_calendar):
        response = await client.get("/external-calendars", headers=admin_headers)

        assert response.status_code == 200
        assert [item["name"] for item in response.json()] == ["Airbnb"]

    async def test_requires_authentication(self, client, external_calendar):
        assert (await client.get("/external-calendars")).status_code == 401


class TestUpdateExternalCalendar:
    async def test_updates_name_and_url(self, client, admin_headers, external_calendar):
        response = await client.put(
            f"/external-calendars/{external_calendar.id}",
            json=_payload(name="Airbnb (renamed)", url="https://example.com/new.ics"),
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Airbnb (renamed)"
        assert response.json()["url"] == "https://example.com/new.ics"

    async def test_keeps_the_export_token(self, client, admin_headers, external_calendar):
        """Rotating it would silently break whatever the host already pasted
        into the platform's "sync calendars" setting."""
        response = await client.put(
            f"/external-calendars/{external_calendar.id}",
            json=_payload(name="Renamed"),
            headers=admin_headers,
        )

        assert response.json()["export_token"] == external_calendar.export_token

    async def test_missing_calendar_is_404(self, client, admin_headers):
        response = await client.put(
            "/external-calendars/000000000000000000000000", json=_payload(), headers=admin_headers
        )
        assert response.status_code == 404


class TestDeleteExternalCalendar:
    async def test_deletes_the_calendar(self, client, admin_headers, external_calendar):
        response = await client.delete(f"/external-calendars/{external_calendar.id}", headers=admin_headers)

        assert response.status_code == 204
        assert await ExternalCalendar.get(external_calendar.id) is None

    async def test_requires_admin(self, client, guest_headers, external_calendar):
        response = await client.delete(f"/external-calendars/{external_calendar.id}", headers=guest_headers)
        assert response.status_code == 403


class TestSyncNow:
    @pytest.fixture(autouse=True)
    def feed(self, monkeypatch):
        responses: dict[str, bytes] = {}

        async def _fake_fetch(url: str) -> bytes:
            return responses[url]

        monkeypatch.setattr(calendar_sync, "fetch_calendar_feed", _fake_fetch)
        return responses

    @staticmethod
    def _ics(uid: str, begin: str, end: str) -> bytes:
        return (
            "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Test//EN\n"
            f"BEGIN:VEVENT\nUID:{uid}\nDTSTART;VALUE=DATE:{begin}\nDTEND;VALUE=DATE:{end}\nEND:VEVENT\n"
            "END:VCALENDAR\n"
        ).encode()

    async def test_syncs_one_calendar_on_demand(self, client, admin_headers, external_calendar, feed):
        feed[external_calendar.url] = self._ics("a@airbnb.com", "20260901", "20260905")

        response = await client.post(
            f"/external-calendars/{external_calendar.id}/sync", headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["created"] == 1
        assert body["calendar_name"] == "Airbnb"
        assert await Closure.find_all().count() == 1

    async def test_syncs_every_calendar_on_demand(
        self, client, admin_headers, external_calendar, other_external_calendar, feed
    ):
        feed[external_calendar.url] = self._ics("a@airbnb.com", "20260901", "20260905")
        feed[other_external_calendar.url] = self._ics("b@booking.com", "20261001", "20261005")

        response = await client.post("/external-calendars/sync", headers=admin_headers)

        assert response.status_code == 200
        assert {item["calendar_name"] for item in response.json()} == {"Airbnb", "Booking.com"}
        assert await Closure.find_all().count() == 2

    async def test_reports_a_failing_feed_without_failing_the_request(
        self, client, admin_headers, external_calendar, feed
    ):
        """The admin needs to see *which* feed is broken, so a bad URL is a
        200 with an error result rather than a 5xx."""
        response = await client.post(
            f"/external-calendars/{external_calendar.id}/sync", headers=admin_headers
        )

        assert response.status_code == 200
        assert response.json()["status"] == "error"
        assert response.json()["error"]

    async def test_missing_calendar_is_404(self, client, admin_headers):
        response = await client.post(
            "/external-calendars/000000000000000000000000/sync", headers=admin_headers
        )
        assert response.status_code == 404

    async def test_requires_admin(self, client, guest_headers, external_calendar):
        response = await client.post(
            f"/external-calendars/{external_calendar.id}/sync", headers=guest_headers
        )
        assert response.status_code == 403
