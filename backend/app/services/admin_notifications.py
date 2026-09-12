"""Admin-facing booking/payment notifications — email *and* SMS, to every
admin in the admins collection.

Triggered from the same places that own each piece of state, so a
notification can never claim something the database doesn't say: the Stripe
webhook handlers in app.api.routes.payments (the sole writers of
payment_status/charges) and the cancellation endpoint in
app.api.routes.bookings. The events:

- booking_confirmed         — the booking just went Active: a SetupIntent was
                              verified (free-cancellation booking, nothing
                              charged) or the opening charge succeeded.
- payment_received          — any later successful charge: scheduled_accrual
                              from the daily reconciliation job, or
                              cancellation_settlement.
- payment_failed            — a charge was declined, or needs guest-side 3DS.
- card_verification_failed  — a SetupIntent failed; nothing was charged.
- booking_cancelled         — the guest or an admin cancelled the booking.
- booking_rejected          — the booking lost the availability race after
                              being paid for, and reports whether the refund
                              actually went through.
- payment_refunded          — a late payment landed on a booking that was
                              already cancelled, and was handed back.

Deliberately *not* notified on: a Pending booking being created, edited or
swept away. One is created the moment a guest reaches checkout, holds its
nights for only settings.pending_booking_ttl_minutes, and most are simply
abandoned — an SMS per abandoned checkout would be the bulk of the traffic
while reporting that nothing happened. Every Pending booking that turns into
something does so through one of the events above.

The SMS is deliberately terse (what happened, guest, dates, price); the email
carries the full booking and guest detail. Wording for both lives in
backend/data/en/ — admin notifications are always in the default language,
since Admin carries no language preference, unlike Guest.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from app.core.config import settings
from app.core.notifications import send_html_email, send_sms
from app.models.admin import Admin
from app.models.booking import Booking, BookingCharge
from app.models.guest import Currency, Guest, Language
from app.services import currency_service, email_templates

logger = logging.getLogger(__name__)

AdminNotificationEvent = Literal[
    "booking_confirmed",
    "payment_received",
    "payment_failed",
    "card_verification_failed",
    "booking_cancelled",
    "booking_rejected",
    "payment_refunded",
]

# Admins have no preferred_language (see the module docstring), so both
# templates and the event labels are always read from the default language's
# directory.
_ADMIN_LANGUAGE: Language = "en"

_EMAIL_TEMPLATE = "admin_notification.html"
_SMS_TEMPLATE = "admin_notification_sms.txt"

# Every amount whose CHF equivalent this module shows is reported as "None"
# when the figure isn't available — either because the booking is already in
# CHF (there is no second figure to show) or because the FX lookup failed.
_ToChf = Callable[[Decimal, Currency], Decimal | None]


@lru_cache(maxsize=None)
def _labels(language: Language) -> dict:
    """Admin-facing wording: the headline per event, and the charge-reason
    names. Read from data/<language>/admin_labels.json for the same reason
    the invoice's labels live in data/ (see app.services.invoice) — so
    rewording a notification never touches Python."""
    raw = (email_templates.DATA_DIR / language / "admin_labels.json").read_text(encoding="utf-8")
    return json.loads(raw)


async def _chf_converter(currencies: set[Currency]) -> _ToChf:
    """A synchronous "this amount in CHF, or None" function.

    Rates are fetched once here rather than per amount: a notification
    converts the booking total, the amount charged, the outstanding balance
    and possibly a charge, and awaiting a coroutine per field would be four
    round trips for one message. `rates_for` skips Stripe entirely when every
    amount is already in CHF.

    A failed lookup degrades to "no CHF figure" instead of propagating: the
    CHF column is a convenience, and losing the whole notification because
    Stripe's (preview) FX Quotes API is down would be a far worse trade — the
    guest's own currency is the one the money actually moved in.
    """
    try:
        rates = await currency_service.rates_for(currencies, "CHF")
    except Exception:
        logger.exception("Could not fetch FX rates for an admin notification; omitting the CHF figures")
        return lambda amount, currency: None

    def to_chf(amount: Decimal, currency: Currency) -> Decimal | None:
        # Same currency, nothing to show: "price in guest's currency and CHF
        # if different" means a CHF booking gets one figure, not two.
        if currency == "CHF":
            return None
        return currency_service.convert_amount_with_rates(amount, currency, "CHF", rates)

    return to_chf


def _guest_context(guest: Guest | None) -> dict:
    if guest is None:
        # The booking outlived its guest document. The point of the
        # notification is that an admin hears about the money, so it goes out
        # with the guest fields blank rather than not at all.
        return {
            "guest_name": None,
            "guest_country": None,
            "guest_language": None,
            "guest_phone": None,
            "guest_email": None,
            "guest_redacted": False,
        }
    return {
        "guest_name": f"{guest.first_name} {guest.family_name}".strip(),
        "guest_country": guest.residence_address.country,
        "guest_language": guest.preferred_language,
        "guest_phone": guest.phone_number,
        "guest_email": guest.email,
        # A guest wiped by the retention sweep (see app.services.data_retention)
        # carries redacted placeholders in every field above. Flagged so an
        # admin reads them as "no longer kept" rather than puzzling over them.
        "guest_redacted": guest.is_redacted,
    }


def _charge_context(charge: BookingCharge | None, to_chf: _ToChf, labels: dict) -> dict | None:
    if charge is None:
        return None
    return {
        "reason": labels["charge_reasons"].get(charge.reason, charge.reason),
        "amount": charge.amount,
        "currency": charge.currency,
        # Stripe's own settlement figure when the balance transaction has
        # already been read (see BookingCharge.amount_chf) — that is the money
        # actually received, so it beats a converted estimate. Falls back to a
        # conversion for a charge whose breakdown hasn't landed yet.
        "amount_chf": charge.amount_chf if charge.amount_chf is not None else to_chf(charge.amount, charge.currency),
        "date": charge.created_at.date().isoformat(),
        "reference": charge.stripe_payment_intent_id,
    }


async def _build_context(
    event: AdminNotificationEvent,
    booking: Booking,
    *,
    charge: BookingCharge | None,
    detail: str | None,
    refunded: bool | None,
) -> dict:
    guest = await booking.resolved_guest()
    labels = _labels(_ADMIN_LANGUAGE)
    currency = booking.currency
    to_chf = await _chf_converter({currency, *([charge.currency] if charge else [])})

    # A booking with no date ranges is reachable (BookingCreate.date_ranges
    # defaults to empty), and min()/max() over nothing raises — which in a
    # notification would mean silently losing the one message telling an admin
    # money moved.
    check_in = min((r.begin_date for r in booking.date_ranges), default=None)
    check_out = max((r.end_date for r in booking.date_ranges), default=None)
    outstanding = booking.total_price - booking.amount_charged

    return {
        "business_name": settings.business_name,
        "event": event,
        "event_label": labels["events"].get(event, event),
        "booking_id": str(booking.id),
        "booking_status": labels["booking_statuses"].get(booking.status, booking.status),
        "payment_status": labels["payment_statuses"].get(booking.payment_status, booking.payment_status),
        "check_in": check_in.isoformat() if check_in else None,
        "check_out": check_out.isoformat() if check_out else None,
        "nights": sum((r.end_date - r.begin_date).days for r in booking.date_ranges),
        # Every stay this app books is a single range today; listed anyway so a
        # split stay isn't reported as one continuous block of dates.
        "date_ranges": [
            {"begin_date": r.begin_date.isoformat(), "end_date": r.end_date.isoformat()}
            for r in sorted(booking.date_ranges, key=lambda r: r.begin_date)
        ],
        "currency": currency,
        "total_price": booking.total_price,
        "total_price_chf": to_chf(booking.total_price, currency),
        "total_discount": booking.total_discount,
        "amount_charged": booking.amount_charged,
        "amount_charged_chf": to_chf(booking.amount_charged, currency),
        "outstanding": outstanding,
        "outstanding_chf": to_chf(outstanding, currency),
        "cancellation_policy_name": booking.cancellation_policy.name,
        # The whole code -> name map, not just this guest's: the template needs
        # it to spell out `guest_language`, which may be unset.
        "languages": labels["languages"],
        "charge": _charge_context(charge, to_chf, labels),
        # The Stripe-reported reason a payment or verification failed, and —
        # for a rejected booking — whether its refund actually went through.
        # `refunded` is None when there was no money to hand back.
        "detail": detail,
        "refunded": refunded,
        **_guest_context(guest),
    }


async def _deliver(*, subject: str, html_content: str, sms_body: str) -> None:
    """One email and one SMS to every admin, all in flight together and each
    isolated from the others: a bad phone number on one admin's record must
    not cost the other admin their email."""
    admins = await Admin.find_all().to_list()
    if not admins:
        logger.warning("No admins on record to notify: %s", subject)
        return

    sends: list[tuple[str, str, object]] = []
    for admin in admins:
        sends.append(("email", admin.email, send_html_email(to_address=admin.email, subject=subject, html_content=html_content)))
        sends.append(("SMS", admin.phone_number, send_sms(admin.phone_number, sms_body)))

    outcomes = await asyncio.gather(*(coro for _, _, coro in sends), return_exceptions=True)
    for (channel, recipient, _), outcome in zip(sends, outcomes):
        if isinstance(outcome, BaseException):
            logger.error("Failed to send admin %s to %s: %s", channel, recipient, outcome)


async def notify_admins(
    event: AdminNotificationEvent,
    booking: Booking,
    *,
    charge: BookingCharge | None = None,
    detail: str | None = None,
    refunded: bool | None = None,
) -> None:
    """Tell every admin what just happened to `booking`, by email and SMS.

    Never raises. Most call sites are Stripe webhook handlers, which Stripe
    treats a 5xx from as a failed delivery and redelivers — so a SendGrid
    outage, a Twilio rejection or an FX hiccup must not fail the response, all
    the more so because the state being reported on has already been durably
    written by the time this runs. Self-guarding rather than relying on each
    of the seven call sites to remember a wrapper.
    """
    try:
        context = await _build_context(event, booking, charge=charge, detail=detail, refunded=refunded)
        subject, html_content = email_templates.render_email(
            language=_ADMIN_LANGUAGE, name=_EMAIL_TEMPLATE, context=context
        )
        # Stripped: the template file's trailing newline would otherwise ride
        # along into the message body.
        sms_body = email_templates.render_text(
            language=_ADMIN_LANGUAGE, name=_SMS_TEMPLATE, context=context
        ).strip()
        await _deliver(subject=subject, html_content=html_content, sms_body=sms_body)
    except Exception:
        logger.exception("Failed to notify admins of %s on booking %s", event, booking.id)
