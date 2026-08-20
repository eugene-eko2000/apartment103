from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from beanie import PydanticObjectId

from app.models.booking import Booking, BookingCharge
from app.models.cancellation_policy import CancellationPolicy, CancellationRule
from app.models.closure import Closure
from app.models.payment_event import PaymentEvent
from app.api.routes import payments as payments_routes
from app.services import stripe_service
from app.services.stripe_service import ChargeFeeBreakdown

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
        # Nothing's due yet, but the full amount becomes non-refundable (and
        # thus chargeable) right at check-in per the "Flexible" policy.
        assert body["upcoming_charges"] == [{"charge_date": _future(200), "amount": 1000.0}]

    async def test_partial_fee_zone_returns_payment_intent(self, monkeypatch, client, guest, guest_headers):
        policy = await _flat_fee_policy(0.5)
        booking_id = await _create_booking(client, guest, policy, guest_headers, begin_offset=30, price=1000.0)

        async def fake_get_or_create_customer(guest_arg):
            return "cus_test"

        async def fake_create_on_session_payment_intent(
            *, customer_id, amount, currency, metadata
        ):
            assert customer_id == "cus_test"
            assert amount == pytest.approx(500.0)
            assert currency == "CHF"
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
        # The flat-fee policy never becomes any more non-refundable than the
        # 50% already due now, so nothing further is scheduled.
        assert body["upcoming_charges"] == []

    async def test_includes_upcoming_charges_from_schedule(self, monkeypatch, client, guest, guest_headers):
        # Two-stage policy: 50% becomes non-refundable (and due now) as soon
        # as the booking is made, and the remaining 50% becomes non-refundable
        # (and thus due) at the 14-days-before-checkin threshold.
        policy = await CancellationPolicy(
            name="Half now, half at 14 days",
            rules=[
                CancellationRule(days_before_checkin=200, refund_percentage=0.5),
                CancellationRule(days_before_checkin=14, refund_percentage=0.0),
            ],
        ).insert()
        booking_id = await _create_booking(client, guest, policy, guest_headers, begin_offset=300, price=1000.0)

        async def fake_get_or_create_customer(guest_arg):
            return "cus_test"

        async def fake_create_on_session_payment_intent(*, customer_id, amount, currency, metadata):
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
        assert body["upcoming_charges"] == [{"charge_date": _future(101), "amount": 500.0}]

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

    async def test_rejects_and_deletes_booking_colliding_with_active_booking(
        self, client, guest, other_guest, cancellation_policy, guest_headers, other_guest_headers
    ):
        # An Active booking already occupies these dates (e.g. another guest
        # paid first); this Pending one was allowed to be stored (Pending
        # bookings don't block the calendar) but must be rejected, and
        # removed, the moment it tries to actually pay.
        occupying_id = await _create_booking(client, other_guest, cancellation_policy, other_guest_headers)
        occupying = await Booking.get(PydanticObjectId(occupying_id))
        occupying.status = "Active"
        await occupying.save()

        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers)

        response = await client.post(f"/bookings/{booking_id}/payment/intent", headers=guest_headers)
        assert response.status_code == 409
        assert _future(200) in response.json()["detail"]

        follow_up = await client.get(f"/bookings/{booking_id}", headers=guest_headers)
        assert follow_up.status_code == 404

    async def test_rejects_and_deletes_booking_colliding_with_a_closure(
        self, client, guest, cancellation_policy, guest_headers
    ):
        # The dates are taken on another platform (an imported closure, or
        # one the host entered by hand). The guest calendar greys those days
        # out, but a page loaded before the last sync pass wouldn't have —
        # so the block has to hold here too, before money moves.
        await Closure(
            platform="Airbnb",
            begin_date=date.fromisoformat(_future(202)),
            end_date=date.fromisoformat(_future(206)),
        ).insert()

        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers)

        response = await client.post(f"/bookings/{booking_id}/payment/intent", headers=guest_headers)
        assert response.status_code == 409

        follow_up = await client.get(f"/bookings/{booking_id}", headers=guest_headers)
        assert follow_up.status_code == 404

    async def test_ignores_other_pending_bookings_for_the_same_dates(
        self, monkeypatch, client, guest, other_guest, cancellation_policy, guest_headers, other_guest_headers
    ):
        # Another guest also has a Pending (unpaid) booking for the same
        # dates — that alone must not block this guest from paying; only an
        # Active booking should.
        await _create_booking(client, other_guest, cancellation_policy, other_guest_headers)
        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers)

        async def fake_get_or_create_customer(guest_arg):
            return "cus_test"

        async def fake_create_setup_intent(*, customer_id, metadata):
            return SimpleNamespace(client_secret="seti_secret_test")

        monkeypatch.setattr(stripe_service, "get_or_create_customer", fake_get_or_create_customer)
        monkeypatch.setattr(stripe_service, "create_setup_intent", fake_create_setup_intent)
        response = await client.post(f"/bookings/{booking_id}/payment/intent", headers=guest_headers)
        assert response.status_code == 200


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
            *, customer_id, amount, currency, metadata
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
        assert booking.status == "Active"

    async def test_webhook_event_log_is_capped(
        self, monkeypatch, client, guest, cancellation_policy, guest_headers
    ):
        """webhook_events is $push-ed with $slice, so a chatty PaymentIntent
        can't grow the booking document without bound."""
        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers)
        cap = payments_routes._MAX_WEBHOOK_EVENTS

        for i in range(cap + 5):
            event = SimpleNamespace(
                id=f"evt_noise_{i}",
                # An event type with no handler: exercises the plain
                # log-only path through _commit.
                type="payment_intent.created",
                data=SimpleNamespace(object={"id": f"pi_{i}", "metadata": {"booking_id": booking_id}}),
            )
            monkeypatch.setattr(stripe_service, "construct_webhook_event", lambda payload, sig, e=event: e)
            response = await client.post(
                "/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"}
            )
            assert response.status_code == 200

        booking = await Booking.get(PydanticObjectId(booking_id))
        assert len(booking.webhook_events) == cap
        # $slice keeps the most recent entries.
        assert booking.webhook_events[-1].stripe_event_id == f"evt_noise_{cap + 4}"

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
        assert booking.status == "Active"
        assert booking.stripe_payment_method_id == "pm_xyz"
        assert len(booking.charges) == 1
        assert booking.charges[0].stripe_payment_intent_id == "pi_1"
        assert len(booking.webhook_events) == 1
        assert booking.webhook_events[0].stripe_event_id == "evt_pi_1"
        assert booking.webhook_events[0].event_type == "payment_intent.succeeded"
        # The booking stores only a reference; the raw payload lives once, on
        # the PaymentEvent, and is read back via GET /payment-events/{id}.
        payment_event = await PaymentEvent.find_one(PaymentEvent.stripe_event_id == "evt_pi_1")
        assert payment_event is not None
        assert payment_event.data["id"] == "pi_1"

        stored_event = await PaymentEvent.find_one(PaymentEvent.stripe_event_id == "evt_pi_1")
        assert stored_event is not None
        assert stored_event.data["id"] == "pi_1"

    async def test_payment_intent_succeeded_attaches_fee_breakdown(
        self, monkeypatch, client, guest, cancellation_policy, guest_headers
    ):
        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers, price=1000.0)
        event = SimpleNamespace(
            id="evt_pi_fees_1",
            type="payment_intent.succeeded",
            data=SimpleNamespace(
                object={
                    "id": "pi_fees_1",
                    "amount": 100000,
                    "currency": "chf",
                    "metadata": {"booking_id": booking_id, "reason": "initial_charge"},
                }
            ),
        )
        monkeypatch.setattr(stripe_service, "construct_webhook_event", lambda payload, sig: event)

        async def fake_get_charge_fee_breakdown(payment_intent_id):
            assert payment_intent_id == "pi_fees_1"
            return ChargeFeeBreakdown(
                settlement_currency="CHF",
                amount_settlement=978.00,
                exchange_rate=0.93,
                processing_fee_settlement=12.00,
                conversion_fee_settlement=20.00,
                net_settlement=946.00,
            )

        monkeypatch.setattr(stripe_service, "get_charge_fee_breakdown", fake_get_charge_fee_breakdown)

        response = await client.post("/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"})
        assert response.status_code == 200

        booking = await Booking.get(PydanticObjectId(booking_id))
        charge = booking.charges[0]
        assert charge.amount_chf == pytest.approx(978.00)
        assert charge.exchange_rate == pytest.approx(0.93)
        assert charge.processing_fee_chf == pytest.approx(12.00)
        assert charge.conversion_fee_chf == pytest.approx(20.00)
        assert charge.net_amount_chf == pytest.approx(946.00)

    async def test_payment_intent_succeeded_tolerates_fee_breakdown_failure(
        self, monkeypatch, client, guest, cancellation_policy, guest_headers
    ):
        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers, price=1000.0)
        event = SimpleNamespace(
            id="evt_pi_fees_2",
            type="payment_intent.succeeded",
            data=SimpleNamespace(
                object={
                    "id": "pi_fees_2",
                    "amount": 100000,
                    "currency": "chf",
                    "metadata": {"booking_id": booking_id, "reason": "initial_charge"},
                }
            ),
        )
        monkeypatch.setattr(stripe_service, "construct_webhook_event", lambda payload, sig: event)

        async def fake_get_charge_fee_breakdown(payment_intent_id):
            raise RuntimeError("Stripe is down")

        monkeypatch.setattr(stripe_service, "get_charge_fee_breakdown", fake_get_charge_fee_breakdown)

        response = await client.post("/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"})
        assert response.status_code == 200

        booking = await Booking.get(PydanticObjectId(booking_id))
        assert booking.amount_charged == pytest.approx(1000.0)
        assert booking.charges[0].amount_chf is None

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

    async def test_setup_intent_failed_records_error_without_changing_status(
        self, monkeypatch, client, guest, cancellation_policy, guest_headers
    ):
        booking_id = await _create_booking(client, guest, cancellation_policy, guest_headers)
        event = SimpleNamespace(
            id="evt_setup_fail_1",
            type="setup_intent.setup_failed",
            data=SimpleNamespace(
                object={
                    "id": "seti_2",
                    "metadata": {"booking_id": booking_id},
                    "last_setup_error": {"message": "Card was declined"},
                }
            ),
        )
        monkeypatch.setattr(stripe_service, "construct_webhook_event", lambda payload, sig: event)

        response = await client.post("/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"})
        assert response.status_code == 200

        booking = await Booking.get(PydanticObjectId(booking_id))
        assert booking.payment_status == "card_verification_pending"
        assert booking.last_payment_error == "Card was declined"

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

