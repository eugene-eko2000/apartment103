from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.anyio


# The public endpoint only returns promotions that haven't expired, so
# anything meant to show up there is dated relative to today rather than
# pinned to a calendar date that will eventually fall into the past.
def _future_dates(**overrides):
    today = date.today()
    return {
        "begin_date": (today + timedelta(days=30)).isoformat(),
        "end_date": (today + timedelta(days=50)).isoformat(),
        **overrides,
    }


def _promotion_payload(**overrides):
    payload = {
        "name": "Spring escape",
        "begin_date": "2026-04-01",
        "end_date": "2026-04-20",
        "discount_type": "percent",
        "discount_ratio": 0.2,
        "min_stay_days": 4,
        "active": True,
    }
    payload.update(overrides)
    return payload


class TestCreatePromotion:
    async def test_creates_promotion(self, client, admin_headers):
        response = await client.post("/promotions", json=_promotion_payload(), headers=admin_headers)
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Spring escape"
        assert body["discount_type"] == "percent"
        assert body["discount_ratio"] == 0.2
        assert body["min_stay_days"] == 4
        assert body["active"] is True

    async def test_creates_absolute_amount_promotion(self, client, admin_headers):
        response = await client.post(
            "/promotions",
            json=_promotion_payload(
                discount_type="amount", discount_ratio=0.0, discount_amount=30.0, currency="EUR"
            ),
            headers=admin_headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["discount_amount"] == 30.0
        assert body["currency"] == "EUR"

    async def test_rejects_end_date_before_begin_date(self, client, admin_headers):
        response = await client.post(
            "/promotions",
            json=_promotion_payload(begin_date="2026-04-20", end_date="2026-04-01"),
            headers=admin_headers,
        )
        assert response.status_code == 422

    async def test_allows_a_single_day_promotion(self, client, admin_headers):
        # end_date is inclusive, so begin == end is one discounted night.
        response = await client.post(
            "/promotions",
            json=_promotion_payload(begin_date="2026-04-01", end_date="2026-04-01"),
            headers=admin_headers,
        )
        assert response.status_code == 201

    async def test_rejects_percent_promotion_with_no_discount(self, client, admin_headers):
        response = await client.post(
            "/promotions", json=_promotion_payload(discount_ratio=0.0), headers=admin_headers
        )
        assert response.status_code == 422

    async def test_rejects_amount_promotion_with_no_discount(self, client, admin_headers):
        response = await client.post(
            "/promotions",
            json=_promotion_payload(discount_type="amount", discount_ratio=0.0, discount_amount=0.0),
            headers=admin_headers,
        )
        assert response.status_code == 422

    async def test_rejects_discount_ratio_above_one(self, client, admin_headers):
        response = await client.post(
            "/promotions", json=_promotion_payload(discount_ratio=1.5), headers=admin_headers
        )
        assert response.status_code == 422

    async def test_rejects_unknown_discount_type(self, client, admin_headers):
        response = await client.post(
            "/promotions", json=_promotion_payload(discount_type="freebie"), headers=admin_headers
        )
        assert response.status_code == 422

    async def test_requires_admin(self, client, guest_headers):
        response = await client.post("/promotions", json=_promotion_payload(), headers=guest_headers)
        assert response.status_code == 403

    async def test_requires_authentication(self, client):
        response = await client.post("/promotions", json=_promotion_payload())
        assert response.status_code == 401


class TestListPromotions:
    async def test_lists_all_promotions(self, client, promotion, admin_headers):
        response = await client.get("/promotions", headers=admin_headers)
        assert response.status_code == 200
        assert [p["name"] for p in response.json()] == [promotion.name]

    async def test_requires_admin(self, client, guest_headers):
        response = await client.get("/promotions", headers=guest_headers)
        assert response.status_code == 403

    async def test_requires_authentication(self, client):
        response = await client.get("/promotions")
        assert response.status_code == 401


class TestGetPromotion:
    async def test_returns_promotion(self, client, promotion, admin_headers):
        response = await client.get(f"/promotions/{promotion.id}", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["name"] == promotion.name

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.get("/promotions/000000000000000000000000", headers=admin_headers)
        assert response.status_code == 404


class TestUpdatePromotion:
    async def test_updates_promotion_fields(self, client, promotion, admin_headers):
        response = await client.put(
            f"/promotions/{promotion.id}",
            json=_promotion_payload(name="Renamed", discount_ratio=0.5),
            headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Renamed"
        assert body["discount_ratio"] == 0.5

    async def test_can_park_a_promotion_without_deleting_it(self, client, promotion, admin_headers):
        response = await client.put(
            f"/promotions/{promotion.id}", json=_promotion_payload(active=False), headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["active"] is False

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.put(
            "/promotions/000000000000000000000000", json=_promotion_payload(), headers=admin_headers
        )
        assert response.status_code == 404

    async def test_requires_admin(self, client, promotion, guest_headers):
        response = await client.put(
            f"/promotions/{promotion.id}", json=_promotion_payload(), headers=guest_headers
        )
        assert response.status_code == 403


class TestDeletePromotion:
    async def test_deletes_promotion(self, client, promotion, admin_headers):
        response = await client.delete(f"/promotions/{promotion.id}", headers=admin_headers)
        assert response.status_code == 204

        follow_up = await client.get(f"/promotions/{promotion.id}", headers=admin_headers)
        assert follow_up.status_code == 404

    async def test_returns_404_for_unknown_id(self, client, admin_headers):
        response = await client.delete("/promotions/000000000000000000000000", headers=admin_headers)
        assert response.status_code == 404

    async def test_requires_admin(self, client, promotion, guest_headers):
        response = await client.delete(f"/promotions/{promotion.id}", headers=guest_headers)
        assert response.status_code == 403


class TestListPublicPromotions:
    async def test_lists_promotions_without_authentication(self, client, admin_headers):
        await client.post(
            "/promotions", json=_promotion_payload(**_future_dates()), headers=admin_headers
        )
        response = await client.get("/promotions/public")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["name"] == "Spring escape"
        assert body[0]["discount_type"] == "percent"
        assert body[0]["discount_ratio"] == 0.2
        assert body[0]["min_stay_days"] == 4

    async def test_hides_inactive_promotions(self, client, admin_headers):
        await client.post(
            "/promotions", json=_promotion_payload(active=False), headers=admin_headers
        )
        response = await client.get("/promotions/public")
        assert response.json() == []

    async def test_hides_expired_promotions(self, client, admin_headers):
        yesterday = date.today() - timedelta(days=1)
        await client.post(
            "/promotions",
            json=_promotion_payload(
                begin_date=(yesterday - timedelta(days=10)).isoformat(), end_date=yesterday.isoformat()
            ),
            headers=admin_headers,
        )
        response = await client.get("/promotions/public")
        assert response.json() == []

    async def test_keeps_a_promotion_ending_today(self, client, admin_headers):
        today = date.today()
        await client.post(
            "/promotions",
            json=_promotion_payload(
                begin_date=(today - timedelta(days=10)).isoformat(), end_date=today.isoformat()
            ),
            headers=admin_headers,
        )
        response = await client.get("/promotions/public")
        assert len(response.json()) == 1

    async def test_converts_the_discount_amount_into_the_requested_currency(
        self, client, admin_headers
    ):
        await client.post(
            "/promotions",
            json=_promotion_payload(
                **_future_dates(),
                discount_type="amount",
                discount_ratio=0.0,
                discount_amount=100.0,
                currency="CHF",
            ),
            headers=admin_headers,
        )
        response = await client.get("/promotions/public?currency=EUR")
        body = response.json()[0]
        # 100 CHF x 1.06 commission x 2 EUR per CHF.
        assert body["discount_amount"] == 212.0
        assert body["discount_amount_chf"] == 100.0
