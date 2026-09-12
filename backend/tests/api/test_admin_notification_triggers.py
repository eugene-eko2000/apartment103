"""Which booking/payment actions notify the admins, and who gets told.

The webhook handlers are exercised directly rather than through
POST /webhooks/stripe, for the same reason tests/api/test_payment_emails.py
does: the endpoint calls `event.data.object.to_dict()`, which needs a real
stripe.Event. What's under test here is only "does this action fan a
notification out to every admin", not Stripe's envelope.

What the messages say is covered by tests/test_admin_notifications.py.
"""

from datetime import date, timedelta

import pytest
from beanie import PydanticObjectId

from app.api.routes import payments as payments_routes
from app.models.booking import Booking
from app.services import admin_notifications, booking_emails

pytestmark = pytest.mark.anyio


def _future(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


@pytest.fixture
def outbox(monkeypatch) -> dict:
    """Intercepts both channels at the vendor boundary, so a test sees exactly
    who would have been contacted.

    Patched rather than left to the "not configured, log instead" fallback in
    app.core.notifications: this project's backend/.env carries real SendGrid
    and Twilio credentials, so an unpatched send here is a live email and a
    billed SMS. The guest-facing email is stubbed out too, for the same reason.
    """
    box: dict[str, list] = {"emails": [], "sms": []}

    async def fake_email(*, to_address, subject, html_content, attachments=None):
        box["emails"].append({"to": to_address, "subject": subject, "body": html_content})

    async def fake_sms(to_number, body):
        box["sms"].append({"to": to_number, "body": body})

    monkeypatch.setattr(admin_notifications, "send_html_email", fake_email)
    monkeypatch.setattr(admin_notifications, "send_sms", fake_sms)
    monkeypatch.setattr(booking_emails, "send_html_email", fake_email)
    return box


def _admin_emails(outbox: dict, admins) -> list[dict]:
    addresses = {a.email for a in admins}
    return [message for message in outbox["emails"] if message["to"] in addresses]


async def _pending_booking(client, guest, policy, admin_headers, *, price=1000.0, begin_offset=200) -> Booking:
    """A Pending booking for `guest` at an exact, hand-set price.

    Posted with admin credentials because a hand-set price is the admin
    manual-override path — POST /bookings derives the price from stored rates
    for a guest principal (see app.services.booking_pricing). Same reasoning as
    tests/api/test_payment_emails.py.
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
    return await Booking.get(PydanticObjectId(response.json()["_id"]))


class TestEveryAdminIsToldOnBothChannels:
    async def test_a_confirmed_booking_emails_and_texts_every_admin(
        self, outbox, client, guest, cancellation_policy, admin, other_admin, admin_headers
    ):
        booking = await _pending_booking(client, guest, cancellation_policy, admin_headers)

        await payments_routes._apply_setup_succeeded(booking, {"payment_method": "pm_abc"})

        assert {message["to"] for message in _admin_emails(outbox, [admin, other_admin])} == {
            admin.email,
            other_admin.email,
        }
        assert {message["to"] for message in outbox["sms"]} == {admin.phone_number, other_admin.phone_number}
        assert all("New booking confirmed" in message["body"] for message in outbox["sms"])

    async def test_one_admins_unreachable_phone_does_not_cost_the_other_their_email(
        self, outbox, monkeypatch, client, guest, cancellation_policy, admin, other_admin, admin_headers
    ):
        booking = await _pending_booking(client, guest, cancellation_policy, admin_headers)

        async def sms_that_fails_for_one_admin(to_number, body):
            if to_number == admin.phone_number:
                raise RuntimeError("Twilio rejected this number")
            outbox["sms"].append({"to": to_number, "body": body})

        monkeypatch.setattr(admin_notifications, "send_sms", sms_that_fails_for_one_admin)

        await payments_routes._apply_setup_succeeded(booking, {"payment_method": "pm_abc"})

        assert len(_admin_emails(outbox, [admin, other_admin])) == 2
        assert [message["to"] for message in outbox["sms"]] == [other_admin.phone_number]
        # And the payment state it was reporting on is untouched.
        reloaded = await Booking.get(booking.id)
        assert reloaded.payment_status == "card_verified"
        assert reloaded.status == "Active"


class TestEachActionIsReported:
    async def test_initial_charge_reports_a_confirmed_booking(
        self, outbox, client, guest, cancellation_policy, admin, admin_headers
    ):
        booking = await _pending_booking(client, guest, cancellation_policy, admin_headers)

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

        assert "[New booking confirmed]" in _admin_emails(outbox, [admin])[0]["subject"]
        assert "pi_initial" in _admin_emails(outbox, [admin])[0]["body"]

    async def test_a_later_charge_reports_a_payment_received(
        self, outbox, client, guest, cancellation_policy, admin, admin_headers
    ):
        booking = await _pending_booking(client, guest, cancellation_policy, admin_headers)

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

        assert "[Payment received]" in _admin_emails(outbox, [admin])[0]["subject"]
        assert "Charged 500.00 CHF" in outbox["sms"][0]["body"]

    async def test_a_declined_charge_reports_the_failure_and_its_reason(
        self, outbox, client, guest, cancellation_policy, admin, admin_headers
    ):
        booking = await _pending_booking(client, guest, cancellation_policy, admin_headers)

        await payments_routes._apply_failed_charge(
            booking,
            {
                "id": "pi_declined",
                "last_payment_error": {"message": "Your card was declined.", "code": "card_declined"},
            },
        )

        message = _admin_emails(outbox, [admin])[0]
        assert "[Payment failed]" in message["subject"]
        assert "Your card was declined." in message["body"]

    async def test_a_failed_card_verification_is_reported(
        self, outbox, client, guest, cancellation_policy, admin, admin_headers
    ):
        booking = await _pending_booking(client, guest, cancellation_policy, admin_headers)

        await payments_routes._apply_setup_failed(
            booking, {"last_setup_error": {"message": "Your card could not be verified."}}
        )

        message = _admin_emails(outbox, [admin])[0]
        assert "[Card verification failed]" in message["subject"]
        assert "Your card could not be verified." in message["body"]

    async def test_cancelling_a_booking_is_reported(
        self, outbox, client, guest, cancellation_policy, admin, admin_headers, guest_headers
    ):
        booking = await _pending_booking(client, guest, cancellation_policy, admin_headers)

        response = await client.post(f"/bookings/{booking.id}/cancel", headers=guest_headers)
        assert response.status_code == 200

        assert "[Booking cancelled]" in _admin_emails(outbox, [admin])[0]["subject"]
        assert "Booking cancelled" in outbox["sms"][0]["body"]


class TestPendingCheckoutsStayQuiet:
    async def test_creating_a_pending_booking_notifies_nobody(
        self, outbox, client, guest, cancellation_policy, admin, admin_headers
    ):
        """A booking is created the moment a guest reaches checkout and most are
        abandoned — see the module docstring of app.services.admin_notifications
        for why those deliberately don't notify."""
        await _pending_booking(client, guest, cancellation_policy, admin_headers)

        assert outbox["emails"] == []
        assert outbox["sms"] == []
