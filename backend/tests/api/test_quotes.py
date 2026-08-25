import pytest

pytestmark = pytest.mark.anyio


def _plan_payload(guest_id, plan_name, **overrides):
    payload = {
        "guest_id": str(guest_id),
        "plan_name": plan_name,
        "currency": "CHF",
        "date_ranges": [{"begin_date": "2026-07-01", "end_date": "2026-07-05"}],
    }
    payload.update(overrides)
    return payload


def _plan_quote(body, plan_name):
    return next(quote for quote in body["plans"] if quote["plan_name"] == plan_name)


class TestGetStayQuote:
    async def test_quotes_without_authentication(self, client, price, plan):
        response = await client.get("/quotes/public?begin_date=2026-07-01&end_date=2026-07-05")
        assert response.status_code == 200
        body = response.json()
        assert body["currency"] == "CHF"
        assert body["nights"] == 4
        # 200.00 a night at the plan's 0.5 ratio, four nights.
        quote = _plan_quote(body, plan.name)
        assert quote["price"] == 400.0
        assert quote["regular_price"] == 400.0
        assert quote["discount"] == 0.0
        assert quote["price_per_night"] == 100.0
        assert quote["applied_promotions"] == []

    async def test_reports_the_hard_minimum_stay_for_the_check_in_date(self, client, price, plan):
        response = await client.get("/quotes/public?begin_date=2026-07-01&end_date=2026-07-05")
        assert response.json()["min_stay_days"] == price.period.date_ranges[0].min_stay_days

    async def test_applies_an_overlapping_promotion(self, client, price, plan, promotion):
        response = await client.get("/quotes/public?begin_date=2026-07-01&end_date=2026-07-05")
        quote = _plan_quote(response.json(), plan.name)
        # Nights 1–3 are inside the promotion (20% off 100.00), night 4 is not.
        assert quote["regular_price"] == 400.0
        assert quote["price"] == 340.0
        assert quote["discount"] == 60.0
        assert quote["applied_promotions"] == [
            {
                "name": "Summer escape",
                "nights": 3,
                "discount_total": 60.0,
                "discount_type": "percent",
                "discount_ratio": 0.2,
            }
        ]

    async def test_ignores_a_promotion_whose_minimum_stay_is_not_met(
        self, client, price, plan, promotion, admin_headers
    ):
        await client.put(
            f"/promotions/{promotion.id}",
            json={
                "name": promotion.name,
                "begin_date": promotion.begin_date.isoformat(),
                "end_date": promotion.end_date.isoformat(),
                "discount_type": "percent",
                "discount_ratio": 0.2,
                "min_stay_days": 5,
            },
            headers=admin_headers,
        )
        response = await client.get("/quotes/public?begin_date=2026-07-01&end_date=2026-07-05")
        quote = _plan_quote(response.json(), plan.name)
        assert quote["price"] == quote["regular_price"] == 400.0

    async def test_converts_into_the_requested_currency(self, client, price, plan, promotion):
        response = await client.get(
            "/quotes/public?begin_date=2026-07-01&end_date=2026-07-05&currency=EUR"
        )
        quote = _plan_quote(response.json(), plan.name)
        assert quote["price_chf"] == 340.0
        assert quote["regular_price_chf"] == 400.0
        # 340 CHF x 1.06 commission x 2 EUR per CHF.
        assert quote["price"] == 720.8
        assert quote["regular_price"] == 848.0

    async def test_rejects_a_checkout_that_is_not_after_check_in(self, client, price, plan):
        response = await client.get("/quotes/public?begin_date=2026-07-05&end_date=2026-07-05")
        assert response.status_code == 422

    async def test_rejects_dates_with_no_configured_rate(self, client, plan):
        response = await client.get("/quotes/public?begin_date=2026-07-01&end_date=2026-07-05")
        assert response.status_code == 400


class TestGetFromPrice:
    async def test_returns_the_cheapest_nightly_rate_at_the_cheapest_ratio(
        self, client, price, plan
    ):
        response = await client.get("/quotes/public/from")
        assert response.status_code == 200
        body = response.json()
        assert body["regular_price_per_night"] == 100.0
        assert body["price_per_night"] == 100.0
        assert body["promoted"] is False
        assert body["promotion_name"] is None

    async def test_applies_the_best_promotion_on_that_rate_range(
        self, client, price, plan, promotion
    ):
        response = await client.get("/quotes/public/from")
        body = response.json()
        assert body["regular_price_per_night"] == 100.0
        assert body["price_per_night"] == 80.0
        assert body["promoted"] is True
        assert body["promotion_name"] == "Summer escape"

    async def test_404_when_no_rate_is_configured(self, client, plan):
        response = await client.get("/quotes/public/from")
        assert response.status_code == 404


class TestQuoteMatchesTheBookingMadeFromIt:
    """The anti-drift regression test.

    A quote and the booking created from the same dates and plan moments
    later must agree to the cent — they are two calls into the very same
    app.services.booking_pricing.quote_ranges, and this is what keeps them
    that way.
    """

    async def test_quote_equals_the_stored_booking_price(
        self, client, guest, guest_headers, plan, price, promotion
    ):
        quote_response = await client.get("/quotes/public?begin_date=2026-07-01&end_date=2026-07-05")
        quote = _plan_quote(quote_response.json(), plan.name)

        booking_response = await client.post(
            "/bookings", json=_plan_payload(guest.id, plan.name), headers=guest_headers
        )
        assert booking_response.status_code == 201
        stored = booking_response.json()["date_ranges"][0]

        assert stored["price"] == quote["price"]
        assert stored["regular_price"] == quote["regular_price"]
        assert [p["name"] for p in stored["applied_promotions"]] == [
            p["name"] for p in quote["applied_promotions"]
        ]
        assert [p["nights"] for p in stored["applied_promotions"]] == [
            p["nights"] for p in quote["applied_promotions"]
        ]
        assert [p["discount_total"] for p in stored["applied_promotions"]] == [
            p["discount_total"] for p in quote["applied_promotions"]
        ]

    async def test_quote_equals_the_stored_booking_price_in_another_currency(
        self, client, guest, guest_headers, plan, price, promotion
    ):
        quote_response = await client.get(
            "/quotes/public?begin_date=2026-07-01&end_date=2026-07-05&currency=EUR"
        )
        quote = _plan_quote(quote_response.json(), plan.name)

        booking_response = await client.post(
            "/bookings",
            json=_plan_payload(guest.id, plan.name, currency="EUR"),
            headers=guest_headers,
        )
        stored = booking_response.json()["date_ranges"][0]
        assert stored["price"] == quote["price"]
        assert stored["regular_price"] == quote["regular_price"]
