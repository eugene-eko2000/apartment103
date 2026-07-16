import pytest

pytestmark = pytest.mark.anyio


def _price_payload(**overrides):
    payload = {
        "period": {
            "begin_date": "2026-06-01",
            "end_date": "2026-09-01",
            "currency": "CHF",
            "date_ranges": [
                {"begin_date": "2026-06-01", "end_date": "2026-07-01", "daily_rate": 100.0},
                {"begin_date": "2026-07-01", "end_date": "2026-09-01", "daily_rate": 150.0},
            ],
        }
    }
    payload.update(overrides)
    return payload


class TestCreatePrice:
    async def test_creates_price(self, client, admin_headers):
        response = await client.post("/prices", json=_price_payload(), headers=admin_headers)
        assert response.status_code == 201
        body = response.json()
        assert body["period"]["currency"] == "CHF"
        assert len(body["period"]["date_ranges"]) == 2

    async def test_requires_admin(self, client, guest_headers):
        response = await client.post("/prices", json=_price_payload(), headers=guest_headers)
        assert response.status_code == 403

    async def test_requires_authentication(self, client):
        response = await client.post("/prices", json=_price_payload())
        assert response.status_code == 401


class TestListPublicPrices:
    async def test_lists_prices_without_authentication(self, client, admin_headers):
        await client.post("/prices", json=_price_payload(), headers=admin_headers)

        response = await client.get("/prices/public")
        assert response.status_code == 200
        assert len(response.json()) == 1


class TestListPrices:
    async def test_lists_all_prices(self, client, admin_headers):
        await client.post("/prices", json=_price_payload(), headers=admin_headers)
        response = await client.get("/prices", headers=admin_headers)
        assert response.status_code == 200
        assert len(response.json()) == 1

    async def test_requires_admin(self, client, guest_headers):
        response = await client.get("/prices", headers=guest_headers)
        assert response.status_code == 403


class TestGetPrice:
    async def test_returns_price(self, client, admin_headers):
        create_response = await client.post("/prices", json=_price_payload(), headers=admin_headers)
        price_id = create_response.json()["_id"]

        response = await client.get(f"/prices/{price_id}", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["period"]["currency"] == "CHF"

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.get("/prices/000000000000000000000000", headers=admin_headers)
        assert response.status_code == 404


class TestUpdatePrice:
    async def test_updates_price_fields(self, client, admin_headers):
        create_response = await client.post("/prices", json=_price_payload(), headers=admin_headers)
        price_id = create_response.json()["_id"]

        updated_payload = _price_payload()
        updated_payload["period"]["currency"] = "EUR"

        response = await client.put(
            f"/prices/{price_id}", json=updated_payload, headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["period"]["currency"] == "EUR"

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.put(
            "/prices/000000000000000000000000", json=_price_payload(), headers=admin_headers
        )
        assert response.status_code == 404


class TestDeletePrice:
    async def test_deletes_price(self, client, admin_headers):
        create_response = await client.post("/prices", json=_price_payload(), headers=admin_headers)
        price_id = create_response.json()["_id"]

        response = await client.delete(f"/prices/{price_id}", headers=admin_headers)
        assert response.status_code == 204

        follow_up = await client.get(f"/prices/{price_id}", headers=admin_headers)
        assert follow_up.status_code == 404

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.delete("/prices/000000000000000000000000", headers=admin_headers)
        assert response.status_code == 404

    async def test_requires_admin(self, client, admin_headers, guest_headers):
        create_response = await client.post("/prices", json=_price_payload(), headers=admin_headers)
        price_id = create_response.json()["_id"]

        response = await client.delete(f"/prices/{price_id}", headers=guest_headers)
        assert response.status_code == 403
