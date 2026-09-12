"""What the admin alerts actually say — app.services.admin_notifications.

Delivery (who gets them, and off the back of which booking/payment action) is
covered by tests/api/test_admin_notification_triggers.py, which needs a database.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.models.booking import (
    Booking,
    BookingCancellationPolicy,
    BookingCharge,
    BookingDateRange,
)
from app.models.cancellation_policy import CancellationRule
from app.models.guest import Currency
from app.services import admin_notifications, currency_service
from tests.booking_factories import guest

pytestmark = pytest.mark.anyio

CHECK_IN = date(2026, 7, 1)
CHECK_OUT = date(2026, 7, 5)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def fixed_rates(monkeypatch):
    """The same deliberately round table the route tests use (see
    tests/api/conftest.py), so a converted figure can be verified by hand:
    2 EUR to 1 CHF. commission_rate is irrelevant here — converting *into*
    CHF carries no markup (see currency_service.convert_amount_with_rates)."""

    async def fake_get_exchange_rates():
        return {"CHF": Decimal("1"), "EUR": Decimal("2"), "USD": Decimal("4"), "GBP": Decimal("0.8")}

    monkeypatch.setattr(currency_service, "get_exchange_rates", fake_get_exchange_rates)


def _booking(currency: Currency = "EUR", price: float = 800.0) -> Booking:
    stay_guest = guest(preferred_language="de")
    stay_guest.residence_address.country = "DE"
    return Booking(
        guest=stay_guest,
        currency=currency,
        date_ranges=[BookingDateRange(begin_date=CHECK_IN, end_date=CHECK_OUT, price=price)],
        cancellation_policy=BookingCancellationPolicy(
            name="Flexible", rules=[CancellationRule(days_before_checkin=14, refund_percentage=1.0)]
        ),
    )


def _charge(amount: float = 200.0, currency: Currency = "EUR", **kwargs) -> BookingCharge:
    return BookingCharge(
        stripe_payment_intent_id="pi_test",
        amount=amount,
        currency=currency,
        reason="scheduled_accrual",
        status="succeeded",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        **kwargs,
    )


@pytest.fixture
def sent(monkeypatch) -> dict:
    """Captures the one rendered message, short-circuiting the fan-out to the
    admins collection (which needs a database)."""
    captured: dict = {}

    async def fake_deliver(*, subject, html_content, sms_body):
        captured.update(subject=subject, html_content=html_content, sms_body=sms_body)

    monkeypatch.setattr(admin_notifications, "_deliver", fake_deliver)
    return captured


class TestSms:
    async def test_carries_guest_dates_and_both_currencies(self, sent):
        await admin_notifications.notify_admins("booking_confirmed", _booking())

        assert sent["sms_body"] == (
            "Berg See Home: New booking confirmed\n"
            "Guest Test\n"
            "2026-07-01 to 2026-07-05\n"
            "Total 800.00 EUR (400.00 CHF)"
        )

    async def test_shows_one_figure_for_a_booking_already_in_chf(self, sent):
        await admin_notifications.notify_admins("booking_confirmed", _booking(currency="CHF"))

        assert "Total 800.00 CHF" in sent["sms_body"]
        # One figure, not the same one twice over.
        assert sent["sms_body"].count("CHF") == 1

    async def test_reports_the_charge_alongside_the_total_for_a_payment(self, sent):
        await admin_notifications.notify_admins("payment_received", _booking(), charge=_charge())

        assert "Charged 200.00 EUR (100.00 CHF)" in sent["sms_body"]
        assert "Total 800.00 EUR (400.00 CHF)" in sent["sms_body"]

    async def test_fits_one_gsm7_segment(self, sent):
        await admin_notifications.notify_admins("payment_received", _booking(), charge=_charge())

        # The template's own punctuation has to stay inside GSM-7: one
        # character outside it drops the per-segment limit from 160 to 70 and
        # turns one billed SMS into two. This guards the wording we control --
        # a guest's name is whatever they gave us (and an umlaut is itself
        # GSM-7 encodable), so the fixture name here is deliberately ASCII.
        assert all(ord(character) < 128 for character in sent["sms_body"])
        assert len(sent["sms_body"]) <= 160

    async def test_does_not_html_escape_the_guest_name(self, sent):
        booking = _booking()
        booking.guest.first_name = "Tom &"
        booking.guest.family_name = "Jerry"

        await admin_notifications.notify_admins("booking_confirmed", booking)

        assert "Tom & Jerry" in sent["sms_body"]


class TestEmail:
    async def test_carries_the_full_guest_record(self, sent):
        booking = _booking()

        await admin_notifications.notify_admins("booking_confirmed", booking)

        body = sent["html_content"]
        assert ">Guest Test</td>" in body
        assert ">DE</td>" in body  # residence country
        assert ">German</td>" in body  # preferred_language, spelled out
        assert f">{booking.guest.phone_number}</td>" in body
        assert f">{booking.guest.email}</td>" in body

    async def test_carries_the_price_in_both_currencies(self, sent):
        await admin_notifications.notify_admins("booking_confirmed", _booking())

        assert "800.00 EUR" in sent["html_content"]
        assert "400.00 CHF" in sent["html_content"]

    async def test_reports_outstanding_against_what_is_charged(self, sent):
        booking = _booking()
        booking.amount_charged = Decimal("200.00")

        await admin_notifications.notify_admins("payment_received", booking, charge=_charge())

        assert "200.00 EUR" in sent["html_content"]  # charged so far
        assert "600.00 EUR" in sent["html_content"]  # still outstanding

    async def test_names_the_event_in_the_subject_with_the_guest_and_dates(self, sent):
        await admin_notifications.notify_admins("payment_failed", _booking(), detail="Your card was declined.")

        assert sent["subject"] == "[Payment failed] Guest Test, 2026-07-01 to 2026-07-05"

    async def test_shows_the_stripe_failure_reason(self, sent):
        await admin_notifications.notify_admins("payment_failed", _booking(), detail="Your card was declined.")

        assert "Your card was declined." in sent["html_content"]

    async def test_escapes_guest_supplied_html(self, sent):
        booking = _booking()
        booking.guest.first_name = "<script>alert(1)</script>"

        await admin_notifications.notify_admins("booking_confirmed", booking)

        assert "<script>alert(1)</script>" not in sent["html_content"]
        assert "&lt;script&gt;" in sent["html_content"]

    async def test_prefers_stripes_settled_chf_figure_over_a_converted_one(self, sent):
        # 199.10 is what Stripe actually settled, not 200 EUR / 2.
        await admin_notifications.notify_admins(
            "payment_received", _booking(), charge=_charge(amount_chf=Decimal("199.10"))
        )

        assert "199.10 CHF" in sent["html_content"]
        assert "100.00 CHF" not in sent["html_content"]

    async def test_says_whether_a_rejected_bookings_refund_went_through(self, sent):
        await admin_notifications.notify_admins("booking_rejected", _booking(), refunded=False)

        assert "The refund failed." in sent["html_content"]

    async def test_flags_a_guest_whose_data_the_retention_sweep_erased(self, sent):
        booking = _booking()
        booking.guest.redacted_at = datetime.now(timezone.utc)

        await admin_notifications.notify_admins("booking_cancelled", booking)

        assert "retention policy" in sent["html_content"]


class TestDegradesInsteadOfGoingSilent:
    async def test_still_sends_in_the_guests_currency_when_the_fx_lookup_fails(self, sent, monkeypatch):
        async def exploding_rates():
            raise RuntimeError("Stripe FX Quotes is down")

        monkeypatch.setattr(currency_service, "get_exchange_rates", exploding_rates)

        await admin_notifications.notify_admins("booking_confirmed", _booking())

        assert "Total 800.00 EUR" in sent["sms_body"]
        assert "CHF" not in sent["sms_body"]

    async def test_still_sends_when_the_guest_record_is_gone(self, sent, monkeypatch):
        """A dangling guest link — the guest document deleted out from under the
        booking — must not cost the admins the one message telling them money
        moved."""

        async def dangling_link(self):
            return None

        monkeypatch.setattr(Booking, "resolved_guest", dangling_link)

        await admin_notifications.notify_admins("payment_received", _booking(), charge=_charge())

        assert "Guest unknown" in sent["sms_body"]
        assert "200.00 EUR" in sent["html_content"]

    async def test_a_booking_with_no_date_ranges_does_not_raise(self, sent):
        booking = _booking()
        booking.date_ranges = []

        await admin_notifications.notify_admins("booking_cancelled", booking)

        assert "Dates not set" in sent["sms_body"]

    async def test_notify_admins_swallows_a_delivery_failure(self, monkeypatch, caplog):
        """The call sites are Stripe webhook handlers: a raise here would be a
        5xx, which Stripe redelivers — re-applying an event whose effect is
        already durably stored."""

        async def exploding_deliver(**kwargs):
            raise RuntimeError("SendGrid is down")

        monkeypatch.setattr(admin_notifications, "_deliver", exploding_deliver)

        await admin_notifications.notify_admins("booking_confirmed", _booking())

        assert "Failed to notify admins" in caplog.text
