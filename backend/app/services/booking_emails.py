"""Guest-facing booking/payment emails.

Two triggers, both invoked from the Stripe webhook handlers in
app/api/routes/payments.py (the sole writers of payment_status/charges, so
they're the only place that reliably knows a payment event actually
happened):

- `send_booking_confirmation_email` — once, when a booking's payment is
  first set up: either a SetupIntent is verified with nothing charged (the
  free-cancellation zone), or the on-session `initial_charge` PaymentIntent
  succeeds. Reports the full booking plus current charging status.
- `send_scheduled_payment_email` — on every later successful charge
  (`scheduled_accrual` from the daily reconciliation job, or
  `cancellation_settlement`). Reports that payment plus what's still
  outstanding.

Both attach a PDF invoice (app.services.invoice) for every charge they
report on. The actual wording/markup lives in app.services.email_templates
(backend/data/<language>/...), keyed off the guest's preferred_language;
this module only assembles the data those templates render.
"""

import asyncio
from datetime import timedelta

from beanie import Link

from app.core.config import settings
from app.core.money import to_decimal
from app.core.notifications import EmailAttachment, send_html_email
from app.models.booking import Booking, BookingCharge
from app.models.guest import Guest
from app.services import email_templates
from app.services.invoice import build_charge_invoice_pdf, invoice_number_for


async def _resolve_guest(booking: Booking) -> Guest:
    return await booking.guest.fetch() if isinstance(booking.guest, Link) else booking.guest


def _nightly_rates(booking: Booking) -> list[dict]:
    """One row per calendar night, splitting each date range's price
    evenly across its nights (the booking model only stores a range-level
    price, not a per-night one)."""
    rows: list[dict] = []
    for date_range in sorted(booking.date_ranges, key=lambda r: r.begin_date):
        nights = (date_range.end_date - date_range.begin_date).days or 1
        per_night = to_decimal(date_range.price / nights)
        night = date_range.begin_date
        while night < date_range.end_date:
            rows.append({"date": night.isoformat(), "rate": per_night})
            night += timedelta(days=1)
    return rows


def _pending_schedule(booking: Booking) -> list[dict]:
    pending = sorted(
        (entry for entry in booking.charge_schedule if entry.status == "pending"),
        key=lambda entry: entry.charge_date,
    )
    return [{"date": entry.charge_date.isoformat(), "amount": entry.amount} for entry in pending]


def _cancellation_rules(booking: Booking) -> list[dict]:
    rules = sorted(booking.cancellation_policy.rules, key=lambda r: r.days_before_checkin, reverse=True)
    return [
        {"days_before_checkin": rule.days_before_checkin, "refund_percentage": rule.refund_percentage}
        for rule in rules
    ]


def _booking_context(booking: Booking, guest: Guest) -> dict:
    check_in = min(date_range.begin_date for date_range in booking.date_ranges)
    check_out = max(date_range.end_date for date_range in booking.date_ranges)
    return {
        "business_name": settings.business_name,
        "guest_first_name": guest.first_name,
        "booking_id": str(booking.id),
        "currency": booking.currency,
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "total_price": booking.total_price,
        "nightly_rates": _nightly_rates(booking),
        "cancellation_policy_name": booking.cancellation_policy.name,
        "cancellation_rules": _cancellation_rules(booking),
        "amount_charged": booking.amount_charged,
        "pending_schedule": _pending_schedule(booking),
    }


async def _invoice_attachment(*, booking: Booking, guest: Guest, charge: BookingCharge) -> EmailAttachment:
    """Renders one charge's invoice PDF. build_charge_invoice_pdf is pure CPU
    (FPDF layout) and these run inside the Stripe webhook handler, which
    Stripe times out — so the render is pushed onto a worker thread rather
    than blocking the event loop."""
    content = await asyncio.to_thread(build_charge_invoice_pdf, booking=booking, guest=guest, charge=charge)
    return EmailAttachment(
        filename=f"{invoice_number_for(charge)}.pdf",
        content=content,
        mime_type="application/pdf",
    )


async def send_booking_confirmation_email(booking: Booking) -> None:
    guest = await _resolve_guest(booking)
    attachments = [
        await _invoice_attachment(booking=booking, guest=guest, charge=charge) for charge in booking.charges
    ]

    subject, html_content = email_templates.render_email(
        language=guest.preferred_language,
        name="booking_confirmation.html",
        context=_booking_context(booking, guest),
    )
    await send_html_email(
        to_address=guest.email, subject=subject, html_content=html_content, attachments=attachments
    )


async def send_scheduled_payment_email(booking: Booking, charge: BookingCharge) -> None:
    guest = await _resolve_guest(booking)
    context = {
        **_booking_context(booking, guest),
        "charge_reason": charge.reason,
        "charge_amount": charge.amount,
        "charge_currency": charge.currency,
        "charge_date": charge.created_at.date().isoformat(),
        "charge_reference": charge.stripe_payment_intent_id,
    }
    subject, html_content = email_templates.render_email(
        language=guest.preferred_language,
        name="scheduled_payment.html",
        context=context,
    )
    await send_html_email(
        to_address=guest.email,
        subject=subject,
        html_content=html_content,
        attachments=[await _invoice_attachment(booking=booking, guest=guest, charge=charge)],
    )
