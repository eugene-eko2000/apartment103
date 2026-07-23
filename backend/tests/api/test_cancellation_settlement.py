from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from beanie import PydanticObjectId

from app.models.booking import Booking, BookingCharge
from app.models.cancellation_policy import CancellationPolicy, CancellationRule
from app.services import stripe_service

pytestmark = pytest.mark.anyio


def _future(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


async def _create_booking(client, guest, policy, headers, begin_offset=30, price=1000.0):
    response = await client.post(
        "/bookings",
        json={
            "guest_id": str(guest.id),
            "cancellation_policy_id": str(policy.id),
            "currency": "CHF",
            "date_ranges": [
                {"begin_date": _future(begin_offset), "end_date": _future(begin_offset + 4), "price": price}
            ],
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["_id"]


async def _flat_fee_policy(refund_percentage: float = 0.5) -> CancellationPolicy:
    return await CancellationPolicy(
        name=f"Flat {refund_percentage}",
        rules=[CancellationRule(days_before_checkin=0, refund_percentage=refund_percentage)],
    ).insert()


class TestCancellationSettlement:
    async def test_cancel_charges_outstanding_amount(self, monkeypatch, client, guest, guest_headers):
        policy = await _flat_fee_policy(0.5)
        booking_id = await _create_booking(client, guest, policy, guest_headers, price=1000.0)
        booking = await Booking.get(PydanticObjectId(booking_id))
        booking.stripe_payment_method_id = "pm_test"
        booking.payment_status = "card_verified"
        await booking.save()

        async def fake_get_or_create_customer(guest_arg):
            return "cus_test"

        async def fake_charge_off_session(**kwargs):
            assert kwargs["metadata"]["reason"] == "cancellation_settlement"
            assert kwargs["idempotency_key"] == f"cancellation_settlement:{booking_id}"
            assert kwargs["amount"] == pytest.approx(500.0)
            return SimpleNamespace(id="pi_settle", status="succeeded", amount=50000, currency="chf")

        monkeypatch.setattr(stripe_service, "get_or_create_customer", fake_get_or_create_customer)
        monkeypatch.setattr(stripe_service, "charge_off_session", fake_charge_off_session)

        response = await client.post(f"/bookings/{booking_id}/cancel", headers=guest_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "Cancelled"

    async def test_cancel_with_no_saved_card_still_cancels(
        self, client, guest, cancellation_policy, guest_headers
    ):
        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers)
        response = await client.post(f"/bookings/{booking_id}/cancel", headers=guest_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "Cancelled"

    async def test_cancel_refunds_overcharge(self, monkeypatch, client, guest, guest_headers):
        # The accrual job never charges ahead of what's owed, so amount_charged
        # can only exceed the owed amount if the booking's own snapshotted
        # policy is edited after charging — simulate that directly.
        policy = await _flat_fee_policy(0.0)
        booking_id = await _create_booking(client, guest, policy, guest_headers, price=1000.0)
        booking = await Booking.get(PydanticObjectId(booking_id))
        booking.stripe_payment_method_id = "pm_test"
        booking.amount_charged = 1000.0
        booking.charges.append(
            BookingCharge(
                stripe_payment_intent_id="pi_1",
                amount=1000.0,
                currency="CHF",
                reason="initial_charge",
                status="succeeded",
            )
        )
        booking.payment_status = "fully_charged"
        booking.cancellation_policy.rules = [CancellationRule(days_before_checkin=0, refund_percentage=0.4)]
        await booking.save()

        async def fake_create_refund(*, payment_intent_id, amount, currency):
            assert payment_intent_id == "pi_1"
            assert amount == pytest.approx(400.0)
            return SimpleNamespace(id="re_settle_1")

        monkeypatch.setattr(stripe_service, "create_refund", fake_create_refund)

        response = await client.post(f"/bookings/{booking_id}/cancel", headers=guest_headers)
        assert response.status_code == 200

        booking = await Booking.get(PydanticObjectId(booking_id))
        assert booking.amount_charged == pytest.approx(600.0)
        assert len(booking.refunds) == 1
