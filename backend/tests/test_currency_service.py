import asyncio
from datetime import datetime, timedelta, timezone
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


class TestExchangeRateCache:
    """get_exchange_rates' caching contract: one Stripe call per TTL window
    even under concurrency, and a failed refresh falls back to the last good
    snapshot instead of failing the request."""

    @pytest.fixture(autouse=True)
    def clear_cache(self, monkeypatch):
        # These tests exercise the real get_exchange_rates, so the autouse
        # fake_rates patch above must not apply, and the module cache must
        # start empty.
        monkeypatch.undo()
        monkeypatch.setattr(currency_service, "_cached_rates", None)
        monkeypatch.setattr(currency_service, "_cached_at", None)
        monkeypatch.setattr(currency_service, "_refresh_lock", asyncio.Lock())

    async def test_concurrent_cold_reads_trigger_a_single_fetch(self, monkeypatch):
        calls = 0

        async def slow_fetch():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0)  # let the other waiters queue on the lock
            return dict(_FAKE_RATES)

        monkeypatch.setattr(currency_service, "_fetch_rates", slow_fetch)

        results = await asyncio.gather(*(currency_service.get_exchange_rates() for _ in range(10)))

        assert calls == 1
        assert all(r == _FAKE_RATES for r in results)

    async def test_serves_stale_rates_when_refresh_fails(self, monkeypatch):
        async def failing_fetch():
            raise RuntimeError("Stripe is down")

        monkeypatch.setattr(currency_service, "_cached_rates", dict(_FAKE_RATES))
        # Older than the TTL (so a refresh is attempted) but well inside the
        # hard-stale window.
        monkeypatch.setattr(
            currency_service, "_cached_at", datetime.now(timezone.utc) - timedelta(hours=2)
        )
        monkeypatch.setattr(currency_service, "_fetch_rates", failing_fetch)

        assert await currency_service.get_exchange_rates() == _FAKE_RATES

    async def test_raises_when_refresh_fails_and_cache_is_too_old(self, monkeypatch):
        async def failing_fetch():
            raise RuntimeError("Stripe is down")

        monkeypatch.setattr(currency_service, "_cached_rates", dict(_FAKE_RATES))
        monkeypatch.setattr(
            currency_service, "_cached_at", datetime.now(timezone.utc) - timedelta(days=2)
        )
        monkeypatch.setattr(currency_service, "_fetch_rates", failing_fetch)

        with pytest.raises(RuntimeError):
            await currency_service.get_exchange_rates()

    async def test_raises_when_refresh_fails_with_an_empty_cache(self, monkeypatch):
        async def failing_fetch():
            raise RuntimeError("Stripe is down")

        monkeypatch.setattr(currency_service, "_fetch_rates", failing_fetch)

        with pytest.raises(RuntimeError):
            await currency_service.get_exchange_rates()


class TestRatesFor:
    """rates_for is what keeps hoisting the rate fetch out of a conversion
    loop from turning same-currency responses into a Stripe round trip."""

    async def test_skips_the_fetch_when_nothing_needs_converting(self, monkeypatch):
        async def fail_if_called():
            raise AssertionError("get_exchange_rates should not be called")

        monkeypatch.setattr(currency_service, "get_exchange_rates", fail_if_called)

        assert await currency_service.rates_for({"CHF"}, "CHF") == {}

    async def test_fetches_when_any_target_differs(self):
        assert await currency_service.rates_for({"CHF"}, "CHF", "EUR") == _FAKE_RATES

    async def test_fetches_when_any_source_differs(self):
        assert await currency_service.rates_for({"CHF", "USD"}, "CHF") == _FAKE_RATES
