from types import SimpleNamespace

import pytest
import stripe

from app.services import stripe_service

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _intent_with_balance_transaction(**balance_transaction_kwargs) -> SimpleNamespace:
    defaults = {
        "currency": "chf",
        "amount": 97800,
        "fee": 3200,
        "net": 94600,
        "exchange_rate": None,
        "fee_details": [],
    }
    defaults.update(balance_transaction_kwargs)
    return SimpleNamespace(latest_charge=SimpleNamespace(balance_transaction=SimpleNamespace(**defaults)))


class TestGetChargeFeeBreakdown:
    async def test_splits_processing_and_conversion_fees(self, monkeypatch):
        intent = _intent_with_balance_transaction(
            exchange_rate=0.93,
            fee_details=[
                SimpleNamespace(amount=1200, description="Stripe processing fees"),
                SimpleNamespace(amount=2000, description="Currency conversion fee"),
            ],
        )
        monkeypatch.setattr(stripe.PaymentIntent, "retrieve", lambda *a, **k: intent)

        result = await stripe_service.get_charge_fee_breakdown("pi_1")

        assert result is not None
        assert result.settlement_currency == "CHF"
        assert result.amount_settlement == pytest.approx(978.00)
        assert result.exchange_rate == 0.93
        assert result.processing_fee_settlement == pytest.approx(12.00)
        assert result.conversion_fee_settlement == pytest.approx(20.00)
        assert result.net_settlement == pytest.approx(946.00)

    async def test_chf_charge_has_no_conversion_fee_or_rate(self, monkeypatch):
        intent = _intent_with_balance_transaction(
            fee_details=[SimpleNamespace(amount=3200, description="Stripe processing fees")],
        )
        monkeypatch.setattr(stripe.PaymentIntent, "retrieve", lambda *a, **k: intent)

        result = await stripe_service.get_charge_fee_breakdown("pi_2")

        assert result is not None
        assert result.exchange_rate is None
        assert result.processing_fee_settlement == pytest.approx(32.00)
        assert result.conversion_fee_settlement == pytest.approx(0)

    async def test_empty_fee_details_falls_back_to_whole_fee_as_processing(self, monkeypatch):
        intent = _intent_with_balance_transaction(fee_details=[])
        monkeypatch.setattr(stripe.PaymentIntent, "retrieve", lambda *a, **k: intent)

        result = await stripe_service.get_charge_fee_breakdown("pi_3")

        assert result is not None
        assert result.processing_fee_settlement == pytest.approx(32.00)
        assert result.conversion_fee_settlement == pytest.approx(0)

    async def test_returns_none_when_balance_transaction_missing(self, monkeypatch):
        intent = SimpleNamespace(latest_charge=SimpleNamespace(balance_transaction=None))
        monkeypatch.setattr(stripe.PaymentIntent, "retrieve", lambda *a, **k: intent)

        assert await stripe_service.get_charge_fee_breakdown("pi_4") is None

    async def test_returns_none_when_no_latest_charge(self, monkeypatch):
        intent = SimpleNamespace(latest_charge=None)
        monkeypatch.setattr(stripe.PaymentIntent, "retrieve", lambda *a, **k: intent)

        assert await stripe_service.get_charge_fee_breakdown("pi_5") is None

    async def test_returns_none_when_settlement_currency_is_not_chf(self, monkeypatch, caplog):
        intent = _intent_with_balance_transaction(currency="eur")
        monkeypatch.setattr(stripe.PaymentIntent, "retrieve", lambda *a, **k: intent)

        result = await stripe_service.get_charge_fee_breakdown("pi_6")

        assert result is None
        assert "not CHF" in caplog.text
