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


async def _create_booking(client, guest, policy, headers, begin_offset=200, price=1000.0):
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


class TestCreatePaymentIntent:
    async def test_free_cancellation_zone_returns_setup_intent(
        self, monkeypatch, client, guest, cancellation_policy, guest_headers
    ):
        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers, begin_offset=200)

        async def fake_get_or_create_customer(guest_arg):
            return "cus_test"

        async def fake_create_setup_intent(*, customer_id, metadata):
            assert customer_id == "cus_test"
            assert metadata["booking_id"] == booking_id
            return SimpleNamespace(client_secret="seti_secret_test")

        monkeypatch.setattr(stripe_service, "get_or_create_customer", fake_get_or_create_customer)
        monkeypatch.setattr(stripe_service, "create_setup_intent", fake_create_setup_intent)

        response = await client.post(f"/bookings/{booking_id}/payment/intent", headers=guest_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "setup"
        assert body["client_secret"] == "seti_secret_test"
        assert body["amount"] == 0.0

    async def test_partial_fee_zone_returns_payment_intent(self, monkeypatch, client, guest, guest_headers):
        policy = await _flat_fee_policy(0.5)
        booking_id = await _create_booking(client, guest, policy, guest_headers, begin_offset=30, price=1000.0)

        async def fake_get_or_create_customer(guest_arg):
            return "cus_test"

        async def fake_create_on_session_payment_intent(
            *, customer_id, amount, currency, save_payment_method, metadata
        ):
            assert customer_id == "cus_test"
            assert amount == pytest.approx(500.0)
            assert currency == "CHF"
            assert save_payment_method is True
            assert metadata["reason"] == "initial_charge"
            return SimpleNamespace(client_secret="pi_secret_test")

        monkeypatch.setattr(stripe_service, "get_or_create_customer", fake_get_or_create_customer)
        monkeypatch.setattr(
            stripe_service, "create_on_session_payment_intent", fake_create_on_session_payment_intent
        )

        response = await client.post(f"/bookings/{booking_id}/payment/intent", headers=guest_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "payment"
        assert body["amount"] == pytest.approx(500.0)
        assert body["client_secret"] == "pi_secret_test"

    async def test_returns_400_if_already_set_up(
        self, client, guest, cancellation_policy, guest_headers
    ):
        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers)
        booking = await Booking.get(PydanticObjectId(booking_id))
        booking.payment_status = "card_verified"
        await booking.save()

        response = await client.post(f"/bookings/{booking_id}/payment/intent", headers=guest_headers)
        assert response.status_code == 400

    async def test_requires_authentication(self, client, guest, cancellation_policy, guest_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers)
        response = await client.post(f"/bookings/{booking_id}/payment/intent")
        assert response.status_code == 401

    async def test_guest_cannot_access_other_guest_booking(
        self, client, guest, cancellation_policy, guest_headers, other_guest_headers
    ):
        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers)
        response = await client.post(f"/bookings/{booking_id}/payment/intent", headers=other_guest_headers)
        assert response.status_code == 403

    async def test_returns_404_for_unknown_booking(self, client, admin_headers):
        response = await client.post(
            "/bookings/000000000000000000000000/payment/intent", headers=admin_headers
        )
        assert response.status_code == 404


class TestRetryPayment:
    async def test_retries_when_requires_action(self, monkeypatch, client, guest, guest_headers):
        policy = await _flat_fee_policy(0.5)
        booking_id = await _create_booking(client, guest, policy, guest_headers, begin_offset=30, price=1000.0)
        booking = await Booking.get(PydanticObjectId(booking_id))
        booking.payment_status = "requires_action"
        booking.stripe_payment_method_id = "pm_test"
        await booking.save()

        async def fake_get_or_create_customer(guest_arg):
            return "cus_test"

        async def fake_create_on_session_payment_intent(
            *, customer_id, amount, currency, save_payment_method, metadata
        ):
            assert amount == pytest.approx(500.0)
            assert metadata["reason"] == "scheduled_accrual"
            return SimpleNamespace(client_secret="pi_retry_secret")

        monkeypatch.setattr(stripe_service, "get_or_create_customer", fake_get_or_create_customer)
        monkeypatch.setattr(
            stripe_service, "create_on_session_payment_intent", fake_create_on_session_payment_intent
        )

        response = await client.post(f"/bookings/{booking_id}/payment/retry", headers=guest_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["amount"] == pytest.approx(500.0)
        assert body["client_secret"] == "pi_retry_secret"

    async def test_returns_400_when_not_in_recoverable_state(
        self, client, guest, cancellation_policy, guest_headers
    ):
        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers)
        response = await client.post(f"/bookings/{booking_id}/payment/retry", headers=guest_headers)
        assert response.status_code == 400

    async def test_returns_400_when_nothing_outstanding(self, client, guest, guest_headers):
        policy = await _flat_fee_policy(0.5)
        booking_id = await _create_booking(client, guest, policy, guest_headers, begin_offset=30, price=1000.0)
        booking = await Booking.get(PydanticObjectId(booking_id))
        booking.payment_status = "failed"
        booking.stripe_payment_method_id = "pm_test"
        booking.amount_charged = 500.0  # already matches what's owed
        await booking.save()

        response = await client.post(f"/bookings/{booking_id}/payment/retry", headers=guest_headers)
        assert response.status_code == 400


class TestAdminRefund:
    async def test_admin_can_refund_partial_amount(self, monkeypatch, client, guest, admin_headers, guest_headers):
        policy = await _flat_fee_policy(0.5)
        booking_id = await _create_booking(client, guest, policy, guest_headers, begin_offset=30, price=1000.0)
        booking = await Booking.get(PydanticObjectId(booking_id))
        booking.charges.append(
            BookingCharge(
                stripe_payment_intent_id="pi_1",
                amount=500.0,
                currency="CHF",
                reason="initial_charge",
                status="succeeded",
            )
        )
        booking.amount_charged = 500.0
        booking.payment_status = "partially_charged"
        await booking.save()

        async def fake_create_refund(*, payment_intent_id, amount, currency):
            assert payment_intent_id == "pi_1"
            assert amount == pytest.approx(200.0)
            assert currency == "CHF"
            return SimpleNamespace(id="re_1")

        monkeypatch.setattr(stripe_service, "create_refund", fake_create_refund)

        response = await client.post(
            f"/admin/bookings/{booking_id}/payment/refund",
            json={"amount": 200.0, "reason": "goodwill"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["amount_charged"] == pytest.approx(300.0)
        assert len(body["refunds"]) == 1
        assert body["payment_status"] == "partially_charged"

    async def test_non_admin_forbidden(self, client, guest, cancellation_policy, guest_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers)
        response = await client.post(
            f"/admin/bookings/{booking_id}/payment/refund",
            json={"amount": 10.0, "reason": "x"},
            headers=guest_headers,
        )
        assert response.status_code == 403

    async def test_amount_exceeding_charged_rejected(self, client, guest, admin_headers, guest_headers):
        policy = await _flat_fee_policy(0.5)
        booking_id = await _create_booking(client, guest, policy, guest_headers, begin_offset=30, price=1000.0)
        response = await client.post(
            f"/admin/bookings/{booking_id}/payment/refund",
            json={"amount": 10.0, "reason": "x"},
            headers=admin_headers,
        )
        assert response.status_code == 400


class TestStripeWebhook:
    async def test_missing_signature_header_is_rejected(self, client):
        response = await client.post("/webhooks/stripe", content=b"{}")
        assert response.status_code == 400

    async def test_invalid_signature_is_rejected(self, monkeypatch, client):
        def fake_construct(payload, sig):
            raise ValueError("bad sig")

        monkeypatch.setattr(stripe_service, "construct_webhook_event", fake_construct)
        response = await client.post("/webhooks/stripe", content=b"{}", headers={"stripe-signature": "bad"})
        assert response.status_code == 400

    async def test_setup_intent_succeeded_marks_card_verified(
        self, monkeypatch, client, guest, cancellation_policy, guest_headers
    ):
        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers)
        event = SimpleNamespace(
            id="evt_setup_1",
            type="setup_intent.succeeded",
            data=SimpleNamespace(
                object={"id": "seti_1", "payment_method": "pm_abc", "metadata": {"booking_id": booking_id}}
            ),
        )
        monkeypatch.setattr(stripe_service, "construct_webhook_event", lambda payload, sig: event)

        response = await client.post("/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"})
        assert response.status_code == 200

        booking = await Booking.get(PydanticObjectId(booking_id))
        assert booking.payment_status == "card_verified"
        assert booking.stripe_payment_method_id == "pm_abc"

    async def test_payment_intent_succeeded_records_charge(
        self, monkeypatch, client, guest, cancellation_policy, guest_headers
    ):
        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers, price=1000.0)
        event = SimpleNamespace(
            id="evt_pi_1",
            type="payment_intent.succeeded",
            data=SimpleNamespace(
                object={
                    "id": "pi_1",
                    "amount": 100000,
                    "currency": "chf",
                    "payment_method": "pm_xyz",
                    "metadata": {"booking_id": booking_id, "reason": "initial_charge"},
                }
            ),
        )
        monkeypatch.setattr(stripe_service, "construct_webhook_event", lambda payload, sig: event)

        response = await client.post("/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"})
        assert response.status_code == 200

        booking = await Booking.get(PydanticObjectId(booking_id))
        assert booking.amount_charged == pytest.approx(1000.0)
        assert booking.payment_status == "fully_charged"
        assert booking.stripe_payment_method_id == "pm_xyz"
        assert len(booking.charges) == 1
        assert booking.charges[0].stripe_payment_intent_id == "pi_1"

    async def test_payment_intent_failed_marks_requires_action(
        self, monkeypatch, client, guest, cancellation_policy, guest_headers
    ):
        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers)
        event = SimpleNamespace(
            id="evt_pi_fail_1",
            type="payment_intent.payment_failed",
            data=SimpleNamespace(
                object={
                    "id": "pi_2",
                    "metadata": {"booking_id": booking_id},
                    "last_payment_error": {"code": "authentication_required", "message": "3DS needed"},
                }
            ),
        )
        monkeypatch.setattr(stripe_service, "construct_webhook_event", lambda payload, sig: event)

        response = await client.post("/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"})
        assert response.status_code == 200

        booking = await Booking.get(PydanticObjectId(booking_id))
        assert booking.payment_status == "requires_action"
        assert booking.last_payment_error == "3DS needed"

    async def test_duplicate_event_is_not_double_counted(
        self, monkeypatch, client, guest, cancellation_policy, guest_headers
    ):
        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers, price=1000.0)
        event = SimpleNamespace(
            id="evt_dup_1",
            type="payment_intent.succeeded",
            data=SimpleNamespace(
                object={
                    "id": "pi_dup",
                    "amount": 100000,
                    "currency": "chf",
                    "metadata": {"booking_id": booking_id, "reason": "initial_charge"},
                }
            ),
        )
        monkeypatch.setattr(stripe_service, "construct_webhook_event", lambda payload, sig: event)

        first = await client.post("/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"})
        second = await client.post("/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"})
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["status"] == "duplicate"

        booking = await Booking.get(PydanticObjectId(booking_id))
        assert booking.amount_charged == pytest.approx(1000.0)
        assert len(booking.charges) == 1
