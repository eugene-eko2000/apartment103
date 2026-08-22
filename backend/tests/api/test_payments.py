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
from app.services.availability import DATES_TAKEN_MESSAGE
from app.services.stripe_service import ChargeFeeBreakdown

pytestmark = pytest.mark.anyio


def _future(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


async def _create_booking(client, guest, policy, admin_headers, begin_offset=200, price=1000.0):
    """Create a Pending booking for `guest` with an exact, hand-set price.

    Posted with admin credentials on purpose: a hand-set price is the admin
    manual-override path, and POST /bookings refuses it for a guest
    principal (a guest names a plan and the server derives the price from
    stored rates — see app.services.booking_pricing). These are payment
    tests that need one specific total to assert charge arithmetic against,
    not whatever the rate table would yield, so they take the admin path
    while the booking still belongs to `guest`.
    """
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
        headers=admin_headers,
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
        self, monkeypatch, client, guest, cancellation_policy, guest_headers, admin_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers, begin_offset=200)

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

    async def test_partial_fee_zone_returns_payment_intent(self, monkeypatch, client, guest, guest_headers, admin_headers):
        policy = await _flat_fee_policy(0.5)
        booking_id = await _create_booking(client, guest, policy, admin_headers, begin_offset=30, price=1000.0)

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

    async def test_includes_upcoming_charges_from_schedule(self, monkeypatch, client, guest, guest_headers, admin_headers):
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
        booking_id = await _create_booking(client, guest, policy, admin_headers, begin_offset=300, price=1000.0)

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
        self, client, guest, cancellation_policy, guest_headers, admin_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers)
        booking = await Booking.get(PydanticObjectId(booking_id))
        booking.payment_status = "card_verified"
        await booking.save()

        response = await client.post(f"/bookings/{booking_id}/payment/intent", headers=guest_headers)
        assert response.status_code == 400

    async def test_requires_authentication(self, client, guest, cancellation_policy, guest_headers, admin_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers)
        response = await client.post(f"/bookings/{booking_id}/payment/intent")
        assert response.status_code == 401

    async def test_guest_cannot_access_other_guest_booking(
        self, client, guest, cancellation_policy, guest_headers, other_guest_headers, admin_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers)
        response = await client.post(f"/bookings/{booking_id}/payment/intent", headers=other_guest_headers)
        assert response.status_code == 403

    async def test_returns_404_for_unknown_booking(self, client, admin_headers):
        response = await client.post(
            "/bookings/000000000000000000000000/payment/intent", headers=admin_headers
        )
        assert response.status_code == 404

    async def test_rejects_and_cancels_booking_colliding_with_active_booking(
        self, client, guest, other_guest, cancellation_policy, guest_headers, other_guest_headers, admin_headers):
        # An Active booking already occupies these dates (e.g. another guest
        # paid first); this Pending one was allowed to be stored (Pending
        # bookings don't block the calendar) but must be rejected, and
        # cancelled, the moment it tries to actually pay.
        occupying_id = await _create_booking(client, other_guest, cancellation_policy, admin_headers)
        occupying = await Booking.get(PydanticObjectId(occupying_id))
        occupying.status = "Active"
        await occupying.save()

        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers)

        response = await client.post(f"/bookings/{booking_id}/payment/intent", headers=guest_headers)
        assert response.status_code == 409
        assert _future(200) in response.json()["detail"]

        # Kept on record as Cancelled (not deleted), so a payment the guest
        # confirms anyway still has a booking to be refunded against.
        rejected = await Booking.get(PydanticObjectId(booking_id))
        assert rejected.status == "Cancelled"
        assert rejected.last_payment_error == DATES_TAKEN_MESSAGE
        assert rejected.booked_nights == []

        # ...and paying for it a second time is refused outright.
        retry = await client.post(f"/bookings/{booking_id}/payment/intent", headers=guest_headers)
        assert retry.status_code == 409

    async def test_rejects_and_cancels_booking_colliding_with_a_closure(
        self, client, guest, cancellation_policy, guest_headers, admin_headers):
        # The dates are taken on another platform (an imported closure, or
        # one the host entered by hand). The guest calendar greys those days
        # out, but a page loaded before the last sync pass wouldn't have —
        # so the block has to hold here too, before money moves.
        await Closure(
            platform="Airbnb",
            begin_date=date.fromisoformat(_future(202)),
            end_date=date.fromisoformat(_future(206)),
        ).insert()

        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers)

        response = await client.post(f"/bookings/{booking_id}/payment/intent", headers=guest_headers)
        assert response.status_code == 409

        rejected = await Booking.get(PydanticObjectId(booking_id))
        assert rejected.status == "Cancelled"

    async def test_ignores_other_pending_bookings_for_the_same_dates(
        self, monkeypatch, client, guest, other_guest, cancellation_policy, guest_headers, other_guest_headers, admin_headers):
        # Another guest also has a Pending (unpaid) booking for the same
        # dates — that alone must not block this guest from paying; only an
        # Active booking should.
        await _create_booking(client, other_guest, cancellation_policy, admin_headers)
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers)

        async def fake_get_or_create_customer(guest_arg):
            return "cus_test"

        async def fake_create_setup_intent(*, customer_id, metadata):
            return SimpleNamespace(client_secret="seti_secret_test")

        monkeypatch.setattr(stripe_service, "get_or_create_customer", fake_get_or_create_customer)
        monkeypatch.setattr(stripe_service, "create_setup_intent", fake_create_setup_intent)
        response = await client.post(f"/bookings/{booking_id}/payment/intent", headers=guest_headers)
        assert response.status_code == 200

    async def test_returns_404_when_booking_was_removed(
        self, client, guest, cancellation_policy, guest_headers, admin_headers):
        # A Pending booking that was removed (e.g. by another guest's
        # activation) can no longer be paid for — the "is it still there"
        # check 404s, which the frontend surfaces as "dates were taken".
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers)
        booking = await Booking.get(PydanticObjectId(booking_id))
        await booking.delete()

        response = await client.post(f"/bookings/{booking_id}/payment/intent", headers=guest_headers)
        assert response.status_code == 404


class TestRetryPayment:
    async def test_retries_when_requires_action(self, monkeypatch, client, guest, guest_headers, admin_headers):
        # This booking is still Pending: its opening charge needed 3DS and so
        # never went through, which is why the retry below is labelled the
        # initial charge rather than an accrual.
        policy = await _flat_fee_policy(0.5)
        booking_id = await _create_booking(client, guest, policy, admin_headers, begin_offset=30, price=1000.0)
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
            assert metadata["reason"] == "initial_charge"
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
        self, client, guest, cancellation_policy, guest_headers, admin_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers)
        response = await client.post(f"/bookings/{booking_id}/payment/retry", headers=guest_headers)
        assert response.status_code == 400

    async def test_returns_400_when_nothing_outstanding(self, client, guest, guest_headers, admin_headers):
        policy = await _flat_fee_policy(0.5)
        booking_id = await _create_booking(client, guest, policy, admin_headers, begin_offset=30, price=1000.0)
        booking = await Booking.get(PydanticObjectId(booking_id))
        booking.payment_status = "failed"
        booking.stripe_payment_method_id = "pm_test"
        booking.amount_charged = 500.0  # already matches what's owed
        await booking.save()

        response = await client.post(f"/bookings/{booking_id}/payment/retry", headers=guest_headers)
        assert response.status_code == 400


    async def test_retry_of_an_unpaid_booking_activates_it(
        self, monkeypatch, client, guest, guest_headers, admin_headers):
        # A declined opening charge leaves the booking Pending (see
        # _apply_failed_charge). Recovering it through the retry endpoint is
        # still that opening payment, so the resulting charge must activate
        # the booking and claim its nights — a booking cannot be left paid-for
        # but Pending, invisible to the calendar and unprotected by the index.
        policy = await _flat_fee_policy(0.5)
        booking_id = await _create_booking(client, guest, policy, admin_headers, begin_offset=30, price=1000.0)
        booking = await Booking.get(PydanticObjectId(booking_id))
        await booking.set(
            {Booking.payment_status: "failed", Booking.stripe_payment_method_id: "pm_test"}
        )

        captured: dict = {}

        async def fake_get_or_create_customer(guest_arg):
            return "cus_test"

        async def fake_create_on_session_payment_intent(*, customer_id, amount, currency, metadata):
            captured.update(metadata)
            return SimpleNamespace(client_secret="pi_secret_retry")

        monkeypatch.setattr(stripe_service, "get_or_create_customer", fake_get_or_create_customer)
        monkeypatch.setattr(
            stripe_service, "create_on_session_payment_intent", fake_create_on_session_payment_intent
        )

        response = await client.post(f"/bookings/{booking_id}/payment/retry", headers=guest_headers)
        assert response.status_code == 200
        assert captured["reason"] == "initial_charge"

        booking = await Booking.get(PydanticObjectId(booking_id))
        await payments_routes._apply_successful_charge(booking, {
            "id": "pi_retry",
            "amount": int(response.json()["amount"] * 100),
            "currency": "chf",
            "payment_method": "pm_test",
            "metadata": {"reason": captured["reason"]},
        })

        after = await Booking.get(PydanticObjectId(booking_id))
        assert after.status == "Active"
        assert len(after.booked_nights) == 4

    async def test_retry_on_an_active_booking_stays_an_accrual(
        self, monkeypatch, client, guest, guest_headers, admin_headers):
        # The other side of the same rule: retrying a *scheduled* charge on an
        # already-Active booking must stay labelled an accrual, so it doesn't
        # re-run activation or re-send the booking confirmation.
        policy = await _flat_fee_policy(0.5)
        booking_id = await _create_booking(client, guest, policy, admin_headers, begin_offset=30, price=1000.0)
        booking = await Booking.get(PydanticObjectId(booking_id))
        await booking.set(
            {
                Booking.status: "Active",
                Booking.payment_status: "requires_action",
                Booking.stripe_payment_method_id: "pm_test",
            }
        )

        captured: dict = {}

        async def fake_get_or_create_customer(guest_arg):
            return "cus_test"

        async def fake_create_on_session_payment_intent(*, customer_id, amount, currency, metadata):
            captured.update(metadata)
            return SimpleNamespace(client_secret="pi_secret_retry")

        monkeypatch.setattr(stripe_service, "get_or_create_customer", fake_get_or_create_customer)
        monkeypatch.setattr(
            stripe_service, "create_on_session_payment_intent", fake_create_on_session_payment_intent
        )

        response = await client.post(f"/bookings/{booking_id}/payment/retry", headers=guest_headers)
        assert response.status_code == 200
        assert captured["reason"] == "scheduled_accrual"

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
        self, monkeypatch, client, guest, cancellation_policy, guest_headers, admin_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers)
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
        self, monkeypatch, client, guest, cancellation_policy, guest_headers, admin_headers):
        """webhook_events is $push-ed with $slice, so a chatty PaymentIntent
        can't grow the booking document without bound."""
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers)
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
        self, monkeypatch, client, guest, cancellation_policy, guest_headers, admin_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers, price=1000.0)
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
        self, monkeypatch, client, guest, cancellation_policy, guest_headers, admin_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers, price=1000.0)
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
        self, monkeypatch, client, guest, cancellation_policy, guest_headers, admin_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers, price=1000.0)
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
        self, monkeypatch, client, guest, cancellation_policy, guest_headers, admin_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers)
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
        self, monkeypatch, client, guest, cancellation_policy, guest_headers, admin_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers)
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
        self, monkeypatch, client, guest, cancellation_policy, guest_headers, admin_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers, price=1000.0)
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

    async def test_payment_activation_cancels_overlapping_pending_booking(
        self, monkeypatch, client, guest, other_guest, cancellation_policy, guest_headers, other_guest_headers, admin_headers):
        # Two guests both have Pending bookings for the same dates. When one
        # pays and goes Active, the other's Pending booking is cancelled so
        # they can't also pay for the same dates later — but it stays on
        # record, since that guest may still confirm a payment.
        winner_id = await _create_booking(client, guest, cancellation_policy, admin_headers, price=1000.0)
        loser_id = await _create_booking(client, other_guest, cancellation_policy, admin_headers, price=1000.0)

        event = SimpleNamespace(
            id="evt_win_1",
            type="payment_intent.succeeded",
            data=SimpleNamespace(
                object={
                    "id": "pi_win",
                    "amount": 100000,
                    "currency": "chf",
                    "metadata": {"booking_id": winner_id, "reason": "initial_charge"},
                }
            ),
        )
        monkeypatch.setattr(stripe_service, "construct_webhook_event", lambda p, s: event)

        response = await client.post("/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"})
        assert response.status_code == 200

        winner = await Booking.get(PydanticObjectId(winner_id))
        loser = await Booking.get(PydanticObjectId(loser_id))
        assert winner.status == "Active"
        assert loser is not None
        assert loser.status == "Cancelled"
        assert loser.last_payment_error == DATES_TAKEN_MESSAGE
        assert loser.booked_nights == []

    async def test_setup_activation_cancels_overlapping_pending_booking(
        self, monkeypatch, client, guest, other_guest, cancellation_policy, guest_headers, other_guest_headers, admin_headers):
        # Same as above, but on the SetupIntent (card-verification) path.
        winner_id = await _create_booking(client, guest, cancellation_policy, admin_headers)
        loser_id = await _create_booking(client, other_guest, cancellation_policy, admin_headers)

        event = SimpleNamespace(
            id="evt_setup_win_1",
            type="setup_intent.succeeded",
            data=SimpleNamespace(
                object={"id": "seti_win", "payment_method": "pm_test", "metadata": {"booking_id": winner_id}}
            ),
        )
        monkeypatch.setattr(stripe_service, "construct_webhook_event", lambda p, s: event)

        response = await client.post("/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"})
        assert response.status_code == 200

        winner = await Booking.get(PydanticObjectId(winner_id))
        loser = await Booking.get(PydanticObjectId(loser_id))
        assert winner.status == "Active"
        assert loser is not None
        assert loser.status == "Cancelled"
        assert loser.booked_nights == []

    async def test_payment_for_missing_booking_is_refunded(
        self, monkeypatch, client, guest, cancellation_policy, guest_headers, admin_headers):
        # The guest paid, but their Pending booking was removed by another
        # guest's overlapping activation before this webhook arrived. The
        # charge must be refunded so they don't pay for a booking that's gone.
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers, price=1000.0)
        booking = await Booking.get(PydanticObjectId(booking_id))
        await booking.delete()

        refunded: list[str] = []

        async def fake_refund(payment_intent_id):
            refunded.append(payment_intent_id)
            return SimpleNamespace(id="re_test")

        monkeypatch.setattr(stripe_service, "refund_payment_intent", fake_refund)

        event = SimpleNamespace(
            id="evt_pi_missing_1",
            type="payment_intent.succeeded",
            data=SimpleNamespace(
                object={
                    "id": "pi_missing",
                    "amount": 100000,
                    "currency": "chf",
                    "metadata": {"booking_id": booking_id, "reason": "initial_charge"},
                }
            ),
        )
        monkeypatch.setattr(stripe_service, "construct_webhook_event", lambda p, s: event)

        response = await client.post("/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"})
        assert response.status_code == 200
        assert refunded == ["pi_missing"]

    async def test_simultaneous_activation_is_rejected_by_unique_index(
        self, monkeypatch, client, guest, other_guest, cancellation_policy, guest_headers, other_guest_headers, admin_headers):
        # Simulate the truly-simultaneous interleaving the proactive
        # cancellation cannot catch on its own: disable it so both Pending
        # bookings survive, then run both activation handlers back-to-back.
        # The unique multikey index must reject the second activation.
        async def noop_cancel(booking):
            return 0

        monkeypatch.setattr(payments_routes, "cancel_overlapping_pending_bookings", noop_cancel)

        first_id = await _create_booking(client, guest, cancellation_policy, admin_headers, price=1000.0)
        second_id = await _create_booking(client, other_guest, cancellation_policy, admin_headers, price=1000.0)

        refunded: list[str] = []

        async def fake_refund(payment_intent_id):
            refunded.append(payment_intent_id)
            return SimpleNamespace(id="re_test")

        monkeypatch.setattr(stripe_service, "refund_payment_intent", fake_refund)

        first = await Booking.get(PydanticObjectId(first_id))
        second = await Booking.get(PydanticObjectId(second_id))

        await payments_routes._apply_successful_charge(first, {
            "id": "pi_first",
            "amount": 100000,
            "currency": "chf",
            "payment_method": "pm_first",
            "metadata": {"reason": "initial_charge"},
        })
        await payments_routes._apply_successful_charge(second, {
            "id": "pi_second",
            "amount": 100000,
            "currency": "chf",
            "payment_method": "pm_second",
            "metadata": {"reason": "initial_charge"},
        })

        first_after = await Booking.get(PydanticObjectId(first_id))
        second_after = await Booking.get(PydanticObjectId(second_id))
        assert first_after.status == "Active"
        assert len(first_after.booked_nights) == 4
        assert second_after.status == "Cancelled"
        assert second_after.booked_nights == []
        assert second_after.last_payment_error == DATES_TAKEN_MESSAGE
        assert refunded == ["pi_second"]


    async def test_unrelated_payment_intent_is_not_refunded(self, monkeypatch, client):
        # A succeeded PaymentIntent this app never created — a Stripe
        # dashboard payment link, an invoice, a manual charge — carries no
        # booking_id metadata. It must be logged and ignored, never refunded:
        # keying the "booking is gone, hand the money back" path off
        # `booking is None` alone would silently refund the host's own
        # unrelated income.
        refunded: list[str] = []

        async def fake_refund(payment_intent_id):
            refunded.append(payment_intent_id)
            return SimpleNamespace(id="re_test")

        monkeypatch.setattr(stripe_service, "refund_payment_intent", fake_refund)

        event = SimpleNamespace(
            id="evt_unrelated_1",
            type="payment_intent.succeeded",
            data=SimpleNamespace(
                object={"id": "pi_unrelated", "amount": 500000, "currency": "chf", "metadata": {}}
            ),
        )
        monkeypatch.setattr(stripe_service, "construct_webhook_event", lambda p, s: event)

        response = await client.post("/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"})
        assert response.status_code == 200
        assert refunded == []

    async def test_cancellation_settlement_is_kept_and_does_not_resurrect(
        self, monkeypatch, client, guest, cancellation_policy, guest_headers, admin_headers):
        # Cancelling settles whatever is still owed by charging off-session,
        # and the webhook for that charge is its sole writer (see
        # app.services.payment_reconciliation). Recording it must not flip the
        # booking back to Active, must not re-claim the nights it just
        # released, and above all must not refund the fee the host is owed.
        refunded: list[str] = []

        async def fake_refund(payment_intent_id):
            refunded.append(payment_intent_id)
            return SimpleNamespace(id="re_test")

        monkeypatch.setattr(stripe_service, "refund_payment_intent", fake_refund)

        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers, price=1000.0)
        booking = await Booking.get(PydanticObjectId(booking_id))
        await payments_routes._apply_successful_charge(booking, {
            "id": "pi_initial",
            "amount": 100000,
            "currency": "chf",
            "payment_method": "pm_test",
            "metadata": {"reason": "initial_charge"},
        })

        assert (await client.post(f"/bookings/{booking_id}/cancel", headers=guest_headers)).status_code == 200
        cancelled = await Booking.get(PydanticObjectId(booking_id))
        assert cancelled.status == "Cancelled"
        assert cancelled.booked_nights == []

        await payments_routes._apply_successful_charge(cancelled, {
            "id": "pi_settlement",
            "amount": 50000,
            "currency": "chf",
            "payment_method": "pm_test",
            "metadata": {"reason": "cancellation_settlement"},
        })

        settled = await Booking.get(PydanticObjectId(booking_id))
        assert settled.status == "Cancelled"
        assert settled.booked_nights == []
        assert refunded == []
        assert [charge.stripe_payment_intent_id for charge in settled.charges] == ["pi_initial", "pi_settlement"]

    async def test_cancelled_booking_does_not_reclaim_released_nights(
        self, monkeypatch, client, guest, other_guest, cancellation_policy, guest_headers, other_guest_headers, admin_headers):
        # The nights a cancellation released are genuinely free: another guest
        # takes them, and the first booking's late settlement webhook must not
        # fight them for it (which would refund a fee that is owed, and leave
        # a bogus "dates no longer available" on a booking the guest cancelled
        # themselves).
        refunded: list[str] = []

        async def fake_refund(payment_intent_id):
            refunded.append(payment_intent_id)
            return SimpleNamespace(id="re_test")

        monkeypatch.setattr(stripe_service, "refund_payment_intent", fake_refund)

        first_id = await _create_booking(client, guest, cancellation_policy, admin_headers, price=1000.0)
        first = await Booking.get(PydanticObjectId(first_id))
        await payments_routes._apply_successful_charge(first, {
            "id": "pi_first", "amount": 100000, "currency": "chf",
            "payment_method": "pm_first", "metadata": {"reason": "initial_charge"},
        })
        await client.post(f"/bookings/{first_id}/cancel", headers=guest_headers)

        # The freed dates are taken by someone else.
        second_id = await _create_booking(client, other_guest, cancellation_policy, admin_headers, price=1000.0)
        second = await Booking.get(PydanticObjectId(second_id))
        await payments_routes._apply_successful_charge(second, {
            "id": "pi_second", "amount": 100000, "currency": "chf",
            "payment_method": "pm_second", "metadata": {"reason": "initial_charge"},
        })
        assert (await Booking.get(PydanticObjectId(second_id))).status == "Active"

        # Now the first booking's settlement webhook finally lands.
        first = await Booking.get(PydanticObjectId(first_id))
        await payments_routes._apply_successful_charge(first, {
            "id": "pi_first_settle", "amount": 50000, "currency": "chf",
            "payment_method": "pm_first", "metadata": {"reason": "cancellation_settlement"},
        })

        assert refunded == []
        first_after = await Booking.get(PydanticObjectId(first_id))
        assert first_after.status == "Cancelled"
        assert first_after.last_payment_error is None
        # The winner keeps its nights.
        assert len((await Booking.get(PydanticObjectId(second_id))).booked_nights) == 4

    async def test_opening_payment_for_cancelled_booking_is_refunded(
        self, monkeypatch, client, guest, cancellation_policy, guest_headers, admin_headers):
        # The mirror case: a booking cancelled by a lost race (or by the
        # guest) whose *opening* payment lands anyway. Here the guest really
        # is paying for dates they won't get, so it must be handed back.
        refunded: list[str] = []

        async def fake_refund(payment_intent_id):
            refunded.append(payment_intent_id)
            return SimpleNamespace(id="re_test")

        monkeypatch.setattr(stripe_service, "refund_payment_intent", fake_refund)

        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers, price=1000.0)
        booking = await Booking.get(PydanticObjectId(booking_id))
        await booking.set({Booking.status: "Cancelled"})

        booking = await Booking.get(PydanticObjectId(booking_id))
        await payments_routes._apply_successful_charge(booking, {
            "id": "pi_late", "amount": 100000, "currency": "chf",
            "payment_method": "pm_test", "metadata": {"reason": "initial_charge"},
        })

        assert refunded == ["pi_late"]
        after = await Booking.get(PydanticObjectId(booking_id))
        assert after.status == "Cancelled"
        assert after.booked_nights == []
        assert after.charges == []

    async def test_setup_intent_does_not_resurrect_cancelled_booking(
        self, monkeypatch, client, guest, cancellation_policy, guest_headers, admin_headers):
        # A SetupIntent only verifies a card, so there is nothing to refund —
        # but it must still not reactivate a booking that is already off the
        # table, nor re-claim its nights.
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers)
        booking = await Booking.get(PydanticObjectId(booking_id))
        await booking.set({Booking.status: "Cancelled"})

        booking = await Booking.get(PydanticObjectId(booking_id))
        await payments_routes._apply_setup_succeeded(booking, {"payment_method": "pm_test"})

        after = await Booking.get(PydanticObjectId(booking_id))
        assert after.status == "Cancelled"
        assert after.booked_nights == []
