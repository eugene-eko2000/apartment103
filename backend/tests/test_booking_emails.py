from datetime import date, timedelta

import pytest

from app.models.booking import (
    Booking,
    BookingCancellationPolicy,
    BookingCharge,
    BookingChargeScheduleEntry,
    BookingDateRange,
)
from app.models.cancellation_policy import CancellationRule
from app.services import booking_emails
from tests.booking_factories import guest

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _booking() -> Booking:
    check_in = date.today() + timedelta(days=30)
    return Booking(
        guest=guest(),
        currency="CHF",
        date_ranges=[
            BookingDateRange(begin_date=check_in, end_date=check_in + timedelta(days=3), price=300.0)
        ],
        cancellation_policy=BookingCancellationPolicy(
            name="Standard",
            rules=[CancellationRule(days_before_checkin=14, refund_percentage=1.0)],
        ),
    )


def test_nightly_rates_splits_range_price_evenly_per_night():
    b = _booking()
    rows = booking_emails._nightly_rates(b)

    assert [row["date"] for row in rows] == [
        b.date_ranges[0].begin_date.isoformat(),
        (b.date_ranges[0].begin_date + timedelta(days=1)).isoformat(),
        (b.date_ranges[0].begin_date + timedelta(days=2)).isoformat(),
    ]
    assert all(row["rate"] == pytest.approx(100.0) for row in rows)


def test_pending_schedule_excludes_done_and_sorts_by_date():
    b = _booking()
    b.charge_schedule = [
        BookingChargeScheduleEntry(charge_date=date.today() + timedelta(days=20), amount=50.0, status="pending"),
        BookingChargeScheduleEntry(charge_date=date.today(), amount=100.0, status="done"),
        BookingChargeScheduleEntry(charge_date=date.today() + timedelta(days=5), amount=25.0, status="pending"),
    ]

    pending = booking_emails._pending_schedule(b)

    assert [entry["amount"] for entry in pending] == [25.0, 50.0]


async def test_confirmation_email_escapes_guest_supplied_html(monkeypatch):
    b = _booking()
    b.guest.first_name = "<script>alert(1)</script>"
    captured = {}

    async def fake_send(*, to_address, subject, html_content, attachments):
        captured["to_address"] = to_address
        captured["html_content"] = html_content
        captured["attachments"] = attachments

    monkeypatch.setattr(booking_emails, "send_html_email", fake_send)

    await booking_emails.send_booking_confirmation_email(b)

    assert "<script>alert(1)</script>" not in captured["html_content"]
    assert "&lt;script&gt;" in captured["html_content"]
    assert captured["to_address"] == b.guest.email
    assert captured["attachments"] == []


async def test_confirmation_email_attaches_invoice_for_existing_charges(monkeypatch):
    b = _booking()
    b.charges = [
        BookingCharge(
            stripe_payment_intent_id="pi_1", amount=150.0, currency="CHF", reason="initial_charge", status="succeeded"
        )
    ]
    captured = {}

    async def fake_send(*, to_address, subject, html_content, attachments):
        captured["attachments"] = attachments

    monkeypatch.setattr(booking_emails, "send_html_email", fake_send)

    await booking_emails.send_booking_confirmation_email(b)

    assert len(captured["attachments"]) == 1
    assert captured["attachments"][0].filename == "INV-pi_1.pdf"
    assert captured["attachments"][0].content.startswith(b"%PDF")


async def test_scheduled_payment_email_reports_remaining_payments(monkeypatch):
    b = _booking()
    charge = BookingCharge(
        stripe_payment_intent_id="pi_2", amount=50.0, currency="CHF", reason="scheduled_accrual", status="succeeded"
    )
    b.charges = [charge]
    b.amount_charged = 50.0
    b.charge_schedule = [
        BookingChargeScheduleEntry(charge_date=date.today(), amount=50.0, status="done"),
        BookingChargeScheduleEntry(charge_date=date.today() + timedelta(days=10), amount=250.0, status="pending"),
    ]
    captured = {}

    async def fake_send(*, to_address, subject, html_content, attachments):
        captured["html_content"] = html_content
        captured["attachments"] = attachments

    monkeypatch.setattr(booking_emails, "send_html_email", fake_send)

    await booking_emails.send_scheduled_payment_email(b, charge)

    assert len(captured["attachments"]) == 1
    assert captured["attachments"][0].filename == "INV-pi_2.pdf"
    assert "250.00 CHF" in captured["html_content"]
    assert "pi_2" in captured["html_content"]


async def test_confirmation_email_uses_guest_preferred_language(monkeypatch):
    b = _booking()
    b.guest.preferred_language = "de"
    captured = {}

    async def fake_send(*, to_address, subject, html_content, attachments):
        captured["subject"] = subject
        captured["html_content"] = html_content

    monkeypatch.setattr(booking_emails, "send_html_email", fake_send)

    await booking_emails.send_booking_confirmation_email(b)

    assert captured["subject"] == "Buchung bestätigt — Berg See Home"
    assert "Buchungsreferenz" in captured["html_content"]
