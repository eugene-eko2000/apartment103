from decimal import Decimal

import pytest

from app.core.config import settings
from app.services import currency_service

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


# Deliberately round, easy-to-hand-verify numbers rather than realistic FX
# rates -- these tests are about convert_amount's arithmetic, not real-world
# CHF/EUR/USD/GBP values.
_FAKE_RATES = {
    "CHF": Decimal("1"),
    "EUR": Decimal("2"),
    "USD": Decimal("4"),
    "GBP": Decimal("0.8"),
}


@pytest.fixture(autouse=True)
def fake_rates(monkeypatch):
    async def fake_get_exchange_rates():
        return _FAKE_RATES

    monkeypatch.setattr(currency_service, "get_exchange_rates", fake_get_exchange_rates)


class TestSameCurrency:
    async def test_returns_amount_unchanged(self):
        result = await currency_service.convert_amount(Decimal("42.999"), "CHF", "CHF")
        assert result == Decimal("43.00")

    async def test_does_not_fetch_exchange_rates(self, monkeypatch):
        async def fail_if_called():
            raise AssertionError("get_exchange_rates should not be called for a same-currency conversion")

        monkeypatch.setattr(currency_service, "get_exchange_rates", fail_if_called)

        await currency_service.convert_amount(Decimal("100"), "USD", "USD")


class TestConvertingIntoChf:
    """Converting into the base currency (CHF) never carries a commission,
    regardless of settings.commission_rate."""

    @pytest.mark.parametrize("commission_rate", [Decimal("0"), Decimal("0.025"), Decimal("0.5")])
    async def test_no_commission_applied(self, monkeypatch, commission_rate):
        monkeypatch.setattr(settings, "commission_rate", commission_rate)

        result = await currency_service.convert_amount(Decimal("100"), "EUR", "CHF")

        assert result == Decimal("50.00")


class TestConvertingOutOfChf:
    @pytest.mark.parametrize(
        "commission_rate,expected",
        [
            (Decimal("0"), Decimal("200.00")),
            (Decimal("0.025"), Decimal("205.00")),
            (Decimal("0.10"), Decimal("220.00")),
            (Decimal("0.5"), Decimal("300.00")),
        ],
    )
    async def test_applies_commission_on_top_of_the_rate(self, monkeypatch, commission_rate, expected):
        monkeypatch.setattr(settings, "commission_rate", commission_rate)

        result = await currency_service.convert_amount(Decimal("100"), "CHF", "EUR")

        assert result == expected


class TestConvertingBetweenNonChfCurrencies:
    @pytest.mark.parametrize(
        "commission_rate,expected",
        [
            (Decimal("0"), Decimal("200.00")),
            (Decimal("0.025"), Decimal("205.00")),
        ],
    )
    async def test_applies_commission(self, monkeypatch, commission_rate, expected):
        monkeypatch.setattr(settings, "commission_rate", commission_rate)

        result = await currency_service.convert_amount(Decimal("100"), "EUR", "USD")

        assert result == expected


class TestRounding:
    async def test_result_is_quantized_to_two_places(self, monkeypatch):
        monkeypatch.setattr(settings, "commission_rate", Decimal("0.025"))

        result = await currency_service.convert_amount(Decimal("33.33"), "GBP", "USD")

        # (33.33 / 0.8) * 4 = 166.65, * 1.025 = 170.81625 -> rounds to 170.82
        assert result == Decimal("170.82")
