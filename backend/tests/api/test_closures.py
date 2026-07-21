import pytest

pytestmark = pytest.mark.anyio


def _closure_payload(**overrides):
    payload = {
        "platform": "airbnb",
        "begin_date": "2026-09-01",
        "end_date": "2026-09-05",
    }
    payload.update(overrides)
    return payload


class TestCreateClosure:
    async def test_creates_closure(self, client, admin_headers):
        response = await client.post("/closures", json=_closure_payload(), headers=admin_headers)
        assert response.status_code == 201
        body = response.json()
        assert body["platform"] == "airbnb"
        assert body["begin_date"] == "2026-09-01"
        assert body["end_date"] == "2026-09-05"

    async def test_rejects_end_date_not_after_begin_date(self, client, admin_headers):
        response = await client.post(
            "/closures",
            json=_closure_payload(begin_date="2026-09-05", end_date="2026-09-05"),
            headers=admin_headers,
        )
        assert response.status_code == 422

    async def test_requires_admin(self, client, guest_headers):
        response = await client.post("/closures", json=_closure_payload(), headers=guest_headers)
        assert response.status_code == 403

    async def test_requires_authentication(self, client):
        response = await client.post("/closures", json=_closure_payload())
        assert response.status_code == 401


class TestListPublicClosedDateRanges:
    async def test_lists_date_ranges_without_authentication(self, client, closure):
        response = await client.get("/closures/public/date-ranges")
        assert response.status_code == 200
        assert response.json() == [{"begin_date": "2026-08-01", "end_date": "2026-08-05"}]


class TestListClosures:
    async def test_lists_all_closures(self, client, closure, admin_headers):
        response = await client.get("/closures", headers=admin_headers)
        assert response.status_code == 200
        platforms = {c["platform"] for c in response.json()}
        assert platforms == {closure.platform}

    async def test_requires_admin(self, client, guest_headers):
        response = await client.get("/closures", headers=guest_headers)
        assert response.status_code == 403


class TestGetClosure:
    async def test_returns_closure(self, client, closure, admin_headers):
        response = await client.get(f"/closures/{closure.id}", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["platform"] == closure.platform

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.get("/closures/000000000000000000000000", headers=admin_headers)
        assert response.status_code == 404


class TestUpdateClosure:
    async def test_updates_closure_fields(self, client, closure, admin_headers):
        response = await client.put(
            f"/closures/{closure.id}",
            json=_closure_payload(platform="booking_com"),
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["platform"] == "booking_com"

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.put(
            "/closures/000000000000000000000000",
            json=_closure_payload(),
            headers=admin_headers,
        )
        assert response.status_code == 404


class TestDeleteClosure:
    async def test_deletes_closure(self, client, closure, admin_headers):
        response = await client.delete(f"/closures/{closure.id}", headers=admin_headers)
        assert response.status_code == 204

        follow_up = await client.get(f"/closures/{closure.id}", headers=admin_headers)
        assert follow_up.status_code == 404

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.delete("/closures/000000000000000000000000", headers=admin_headers)
        assert response.status_code == 404

    async def test_requires_admin(self, client, closure, guest_headers):
        response = await client.delete(f"/closures/{closure.id}", headers=guest_headers)
        assert response.status_code == 403
