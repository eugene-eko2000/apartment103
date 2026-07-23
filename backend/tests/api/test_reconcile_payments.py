from datetime import date, timedelta
from types import SimpleNamespace

import pytest
import stripe
from beanie import PydanticObjectId

from app.jobs.reconcile_payments import reconcile_booking_payments
from app.models.booking import Booking
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


class TestReconcileBookingPayments:
    async def test_charges_outstanding_amount_for_verified_booking(self, monkeypatch, client, guest, guest_headers):
        policy = await _flat_fee_policy(0.5)
        booking_id = await _create_booking(client, guest, policy, guest_headers, price=1000.0)
        booking = await Booking.get(PydanticObjectId(booking_id))
        booking.stripe_payment_method_id = "pm_test"
        booking.payment_status = "card_verified"
        await booking.save()

        calls = []

        async def fake_get_or_create_customer(guest_arg):
            return "cus_test"

        async def fake_charge_off_session(
            *, customer_id, payment_method_id, amount, currency, metadata, idempotency_key
        ):
            calls.append((amount, metadata["reason"], idempotency_key))
            return SimpleNamespace(id="pi_accrual_1", status="succeeded", amount=50000, currency="chf")

        monkeypatch.setattr(stripe_service, "get_or_create_customer", fake_get_or_create_customer)
        monkeypatch.setattr(stripe_service, "charge_off_session", fake_charge_off_session)

        await reconcile_booking_payments()

        assert len(calls) == 1
        amount, reason, idempotency_key = calls[0]
        assert amount == pytest.approx(500.0)
        assert reason == "scheduled_accrual"
        assert idempotency_key == f"scheduled_accrual:{booking_id}:{date.today().isoformat()}"

        # A successful off-session charge is only ever applied to the booking
        # by the payment_intent.succeeded webhook, never synchronously here —
        # so amount_charged is still untouched right after the job runs.
        refreshed = await Booking.get(PydanticObjectId(booking_id))
        assert refreshed.amount_charged == 0.0
        assert refreshed.last_payment_check_at is not None

    async def test_skips_booking_without_saved_card(self, monkeypatch, client, guest, guest_headers):
        policy = await _flat_fee_policy(0.5)
        booking_id = await _create_booking(client, guest, policy, guest_headers, price=1000.0)

        def fail_if_called(*args, **kwargs):
            raise AssertionError("should not attempt to charge a booking with no saved card")

        monkeypatch.setattr(stripe_service, "charge_off_session", fail_if_called)

        await reconcile_booking_payments()

        refreshed = await Booking.get(PydanticObjectId(booking_id))
        assert refreshed.amount_charged == 0.0

    async def test_skips_booking_already_fully_charged(self, monkeypatch, client, guest, guest_headers):
        policy = await _flat_fee_policy(0.5)
        booking_id = await _create_booking(client, guest, policy, guest_headers, price=1000.0)
        booking = await Booking.get(PydanticObjectId(booking_id))
        booking.stripe_payment_method_id = "pm_test"
        booking.amount_charged = 500.0  # already equals the accrued 50% for this flat policy
        booking.payment_status = "partially_charged"
        await booking.save()

        def fail_if_called(*args, **kwargs):
            raise AssertionError("should not charge when nothing is outstanding")

        monkeypatch.setattr(stripe_service, "charge_off_session", fail_if_called)

        await reconcile_booking_payments()

    async def test_records_failure_without_raising(self, monkeypatch, client, guest, guest_headers):
        policy = await _flat_fee_policy(0.5)
        booking_id = await _create_booking(client, guest, policy, guest_headers, price=1000.0)
        booking = await Booking.get(PydanticObjectId(booking_id))
        booking.stripe_payment_method_id = "pm_test"
        booking.payment_status = "card_verified"
        await booking.save()

        async def fake_get_or_create_customer(guest_arg):
            return "cus_test"

        async def fake_charge_off_session(**kwargs):
            raise stripe.CardError(message="Your card was declined.", param=None, code="card_declined")

        monkeypatch.setattr(stripe_service, "get_or_create_customer", fake_get_or_create_customer)
        monkeypatch.setattr(stripe_service, "charge_off_session", fake_charge_off_session)

        await reconcile_booking_payments()

        refreshed = await Booking.get(PydanticObjectId(booking_id))
        assert refreshed.payment_status == "failed"
        assert "declined" in refreshed.last_payment_error.lower()
