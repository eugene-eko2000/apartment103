"""Booking/payment email hooks in app.api.routes.payments.

Exercises `_apply_setup_succeeded` / `_apply_successful_charge` directly
rather than through the `/webhooks/stripe` endpoint, since the endpoint's
`event.data.object.to_dict()` call requires a real stripe.Event (the
lightweight SimpleNamespace mocks used elsewhere aren't dict-like enough
for it) — orthogonal to what's under test here, which is only "does a
successful webhook handler trigger the right booking email".
"""

from datetime import date, timedelta

import pytest
from beanie import PydanticObjectId

from app.api.routes import payments as payments_routes
from app.models.booking import Booking
from app.services import booking_emails

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


class TestConfirmationEmailTrigger:
    async def test_setup_intent_succeeded_sends_confirmation_email(
        self, monkeypatch, client, guest, cancellation_policy, guest_headers, admin_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers)
        booking = await Booking.get(PydanticObjectId(booking_id))

        confirmation_calls = []

        async def fake_confirmation(b):
            confirmation_calls.append(b.id)

        monkeypatch.setattr(booking_emails, "send_booking_confirmation_email", fake_confirmation)

        await payments_routes._apply_setup_succeeded(booking, {"payment_method": "pm_abc"})

        assert confirmation_calls == [booking.id]
        assert booking.payment_status == "card_verified"

    async def test_initial_charge_sends_confirmation_email_not_scheduled_email(
        self, monkeypatch, client, guest, cancellation_policy, guest_headers, admin_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers, price=1000.0)
        booking = await Booking.get(PydanticObjectId(booking_id))

        confirmation_calls = []
        scheduled_calls = []

        async def fake_confirmation(b):
            confirmation_calls.append(b.id)

        async def fake_scheduled(b, charge):
            scheduled_calls.append(charge.reason)

        monkeypatch.setattr(booking_emails, "send_booking_confirmation_email", fake_confirmation)
        monkeypatch.setattr(booking_emails, "send_scheduled_payment_email", fake_scheduled)

        await payments_routes._apply_successful_charge(
            booking,
            {
                "id": "pi_initial",
                "amount": 100000,
                "currency": "chf",
                "payment_method": "pm_xyz",
                "metadata": {"reason": "initial_charge"},
            },
        )

        assert confirmation_calls == [booking.id]
        assert scheduled_calls == []

    async def test_scheduled_accrual_sends_scheduled_payment_email_not_confirmation(
        self, monkeypatch, client, guest, cancellation_policy, guest_headers, admin_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers, price=1000.0)
        booking = await Booking.get(PydanticObjectId(booking_id))

        confirmation_calls = []
        scheduled_calls = []

        async def fake_confirmation(b):
            confirmation_calls.append(b.id)

        async def fake_scheduled(b, charge):
            scheduled_calls.append((charge.reason, charge.stripe_payment_intent_id))

        monkeypatch.setattr(booking_emails, "send_booking_confirmation_email", fake_confirmation)
        monkeypatch.setattr(booking_emails, "send_scheduled_payment_email", fake_scheduled)

        await payments_routes._apply_successful_charge(
            booking,
            {
                "id": "pi_accrual",
                "amount": 50000,
                "currency": "chf",
                "payment_method": "pm_xyz",
                "metadata": {"reason": "scheduled_accrual"},
            },
        )

        assert confirmation_calls == []
        assert scheduled_calls == [("scheduled_accrual", "pi_accrual")]

    async def test_email_failure_does_not_break_payment_state_update(
        self, monkeypatch, client, guest, cancellation_policy, guest_headers, admin_headers):
        booking_id = await _create_booking(client, guest, cancellation_policy, admin_headers)
        booking = await Booking.get(PydanticObjectId(booking_id))

        async def failing_confirmation(b):
            raise RuntimeError("SendGrid is down")

        monkeypatch.setattr(booking_emails, "send_booking_confirmation_email", failing_confirmation)

        await payments_routes._apply_setup_succeeded(booking, {"payment_method": "pm_abc"})

        reloaded = await Booking.get(PydanticObjectId(booking_id))
        assert reloaded.payment_status == "card_verified"
        assert reloaded.stripe_payment_method_id == "pm_abc"
