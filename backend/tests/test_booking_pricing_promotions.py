"""The promotion pricing algorithm itself.

Exercised through `quote_ranges_with` against a hand-built PricingSnapshot
rather than through the API: this is arithmetic, and it deserves to be
tested without a database, a plan or a booking in the way. The endpoints
that wrap it have their own tests (tests/api/test_quotes.py, and the
quote-equals-booking regression test there in particular).
"""

from datetime import date
from decimal import Decimal

from beanie import PydanticObjectId

from app.models.price import DateRangeRate, Period, Price
from app.models.promotion import Promotion
from app.schemas.booking import BookingDateRangeInput
from app.services.booking_pricing import PricingSnapshot, quote_ranges_with

# Mirrors the table in tests/api/conftest.py: deliberately round rather than
# realistic, so a converted amount can be verified by hand.
RATES = {
    "CHF": Decimal("1"),
    "EUR": Decimal("2"),
    "USD": Decimal("4"),
    "GBP": Decimal("0.8"),
}


def price(daily_rate: str = "200.00", currency: str = "CHF") -> Price:
    return Price(
        period=Period(
            begin_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            currency=currency,
            date_ranges=[
                DateRangeRate(
                    begin_date=date(2026, 1, 1),
                    end_date=date(2026, 12, 31),
                    daily_rate=Decimal(daily_rate),
                    min_stay_days=1,
                )
            ],
        )
    )


def promotion(**overrides) -> Promotion:
    fields = {
        "name": "Spring escape",
        "begin_date": date(2026, 4, 1),
        "end_date": date(2026, 4, 20),
        "discount_type": "percent",
        "discount_ratio": 0.2,
        "min_stay_days": 1,
    }
    fields.update(overrides)
    result = Promotion(**fields)
    # Un-inserted documents have no id; give them one so a snapshot carries
    # the same provenance it would in production.
    result.id = PydanticObjectId()
    return result


def snapshot(promotions: list[Promotion], prices: list[Price] | None = None) -> PricingSnapshot:
    return PricingSnapshot(
        prices=prices if prices is not None else [price()],
        promotions=promotions,
        rates=RATES,
    )


def stay(begin: date, end: date) -> BookingDateRangeInput:
    return BookingDateRangeInput(begin_date=begin, end_date=end)


def quote(promotions: list[Promotion], begin: date, end: date, ratio="1", prices=None, currency="CHF"):
    return quote_ranges_with(
        snapshot(promotions, prices), [stay(begin, end)], Decimal(ratio), currency
    )[0]


class TestNoPromotion:
    def test_price_is_unchanged_when_nothing_overlaps(self):
        # 200/night x 4 nights x ratio 0.5 — exactly what this stay cost
        # before promotions existed.
        result = quote([], date(2026, 6, 1), date(2026, 6, 5), ratio="0.5")
        assert result.price == Decimal("400.00")
        assert result.regular_price == Decimal("400.00")
        assert result.discount == Decimal("0.00")
        assert result.applied_promotions == []

    def test_promotion_elsewhere_in_the_calendar_is_ignored(self):
        result = quote([promotion()], date(2026, 6, 1), date(2026, 6, 5))
        assert result.price == result.regular_price == Decimal("800.00")


class TestOverlap:
    def test_fully_inside_discounts_every_night(self):
        # 4 nights at 200, 20% off each.
        result = quote([promotion()], date(2026, 4, 5), date(2026, 4, 9))
        assert result.regular_price == Decimal("800.00")
        assert result.price == Decimal("640.00")
        assert result.discount == Decimal("160.00")
        assert [(p.name, p.nights, p.discount_total) for p in result.applied_promotions] == [
            ("Spring escape", 4, Decimal("160.00"))
        ]

    def test_partial_overlap_discounts_only_the_overlapped_nights(self):
        # Nights 19, 20 are inside the promotion (end_date is inclusive);
        # nights 21, 22 are not.
        result = quote([promotion()], date(2026, 4, 19), date(2026, 4, 23))
        assert result.regular_price == Decimal("800.00")
        assert result.price == Decimal("720.00")
        assert result.applied_promotions[0].nights == 2

    def test_checkout_day_is_not_a_night(self):
        # The stay's last night is the 20th; the 21st is checkout, so a
        # promotion covering only the 21st discounts nothing.
        result = quote(
            [promotion(begin_date=date(2026, 4, 21), end_date=date(2026, 4, 30))],
            date(2026, 4, 18),
            date(2026, 4, 21),
        )
        assert result.price == result.regular_price
        assert result.applied_promotions == []


class TestMinStayDays:
    def test_stay_shorter_than_minimum_gets_no_discount(self):
        result = quote([promotion(min_stay_days=4)], date(2026, 4, 5), date(2026, 4, 8))
        assert result.price == result.regular_price == Decimal("600.00")
        assert result.applied_promotions == []

    def test_stay_exactly_at_the_minimum_qualifies(self):
        result = quote([promotion(min_stay_days=4)], date(2026, 4, 5), date(2026, 4, 9))
        assert result.price == Decimal("640.00")

    def test_minimum_counts_the_whole_stay_not_the_overlapped_nights(self):
        # Only two nights fall inside the promotion, but the booking is four
        # nights long — the two conditions are independent.
        result = quote([promotion(min_stay_days=4)], date(2026, 4, 19), date(2026, 4, 23))
        assert result.applied_promotions[0].nights == 2
        assert result.price == Decimal("720.00")


class TestDiscountTypes:
    def test_percent_is_a_fraction_off(self):
        result = quote([promotion(discount_ratio=0.25)], date(2026, 4, 5), date(2026, 4, 7))
        assert result.price == Decimal("300.00")  # 2 x (200 - 50)

    def test_absolute_amount_is_per_night(self):
        result = quote(
            [promotion(discount_type="amount", discount_ratio=0.0, discount_amount=Decimal("30.00"))],
            date(2026, 4, 5),
            date(2026, 4, 8),
        )
        assert result.price == Decimal("510.00")  # 3 x (200 - 30)
        assert result.discount == Decimal("90.00")

    def test_absolute_amount_larger_than_the_rate_clamps_to_zero(self):
        result = quote(
            [promotion(discount_type="amount", discount_ratio=0.0, discount_amount=Decimal("500.00"))],
            date(2026, 4, 5),
            date(2026, 4, 7),
        )
        assert result.price == Decimal("0.00")
        assert result.discount == Decimal("400.00")

    def test_absolute_amount_in_another_currency_converts_through_chf(self):
        # 40 EUR at 2 EUR per CHF is 20 CHF off each of 2 nights.
        result = quote(
            [
                promotion(
                    discount_type="amount",
                    discount_ratio=0.0,
                    discount_amount=Decimal("40.00"),
                    currency="EUR",
                )
            ],
            date(2026, 4, 5),
            date(2026, 4, 7),
        )
        assert result.price == Decimal("360.00")


class TestCompetingPromotions:
    def test_largest_discount_per_night_wins(self):
        small = promotion(name="Small", discount_ratio=0.1)
        large = promotion(name="Large", discount_ratio=0.3)
        result = quote([small, large], date(2026, 4, 5), date(2026, 4, 7))
        assert result.price == Decimal("280.00")  # 2 x (200 - 60)
        assert [p.name for p in result.applied_promotions] == ["Large"]

    def test_percent_and_amount_are_compared_in_chf(self):
        percent = promotion(name="Ten percent", discount_ratio=0.1)  # 20 CHF
        absolute = promotion(
            name="Thirty off",
            discount_type="amount",
            discount_ratio=0.0,
            discount_amount=Decimal("30.00"),
        )
        result = quote([percent, absolute], date(2026, 4, 5), date(2026, 4, 6))
        assert result.price == Decimal("170.00")
        assert [p.name for p in result.applied_promotions] == ["Thirty off"]

    def test_a_stay_can_use_a_different_promotion_on_different_nights(self):
        early = promotion(
            name="Early", begin_date=date(2026, 4, 1), end_date=date(2026, 4, 6), discount_ratio=0.5
        )
        late = promotion(
            name="Late", begin_date=date(2026, 4, 7), end_date=date(2026, 4, 20), discount_ratio=0.1
        )
        # Nights 5, 6 at 50% off; nights 7, 8 at 10% off.
        result = quote([early, late], date(2026, 4, 5), date(2026, 4, 9))
        assert result.price == Decimal("560.00")  # 100 + 100 + 180 + 180
        assert [(p.name, p.nights, p.discount_total) for p in result.applied_promotions] == [
            ("Early", 2, Decimal("200.00")),
            ("Late", 2, Decimal("40.00")),
        ]

    def test_a_tie_resolves_to_the_earliest_beginning_promotion(self):
        later = promotion(name="Later", begin_date=date(2026, 4, 3), discount_ratio=0.2)
        earlier = promotion(name="Earlier", begin_date=date(2026, 4, 1), discount_ratio=0.2)
        result = quote([later, earlier], date(2026, 4, 5), date(2026, 4, 7))
        assert [p.name for p in result.applied_promotions] == ["Earlier"]


class TestInactivePromotions:
    def test_inactive_promotion_is_ignored(self):
        result = quote([promotion(active=False)], date(2026, 4, 5), date(2026, 4, 9))
        assert result.price == result.regular_price == Decimal("800.00")
        assert result.applied_promotions == []


class TestCurrencyConversion:
    def test_totals_are_converted_into_the_requested_currency(self):
        # 4 nights x 200 CHF, 20% off = 640 CHF; into EUR that is
        # 640 x 1.06 (commission) x 2 = 1356.80.
        result = quote([promotion()], date(2026, 4, 5), date(2026, 4, 9), currency="EUR")
        assert result.price_chf == Decimal("640.00")
        assert result.regular_price_chf == Decimal("800.00")
        assert result.price == Decimal("1356.80")
        assert result.regular_price == Decimal("1696.00")
        assert result.applied_promotions[0].discount_total == Decimal("339.20")
