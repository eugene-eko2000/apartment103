"""Automated guest messages: rendering a MessageTemplate for one booking,
working out which bookings a template is due for, and sending it.

Rendering. The admin writes markdown with `{{placeholder}}` tokens. Values
are substituted into the markdown *before* it is rendered, each one
backslash-escaped so a guest named `*Ann*` stays literal text instead of
turning into emphasis. Raw HTML in the markdown is disabled, so neither an
admin's markup nor a guest-supplied value can inject tags into the email.

Scheduling. A template names a day relative to one of the booking's dates.
For a run on day D, a booking is due when its anchor date plus (after) or
minus (before) the offset lands on D. A run also looks back
settings.guest_message_catch_up_days, so a missed run or a failed send is
made up the next day — but never past the day the template was created
(a new "1 day after booking" must not mail every guest who ever booked) nor
before the booking itself was made (a booking made 3 days before check-in
never owed the "7 days before check-in" message).

Sending. Each (template, booking) pair gets one MessageDelivery row,
inserted before anything is sent; its unique index is what stops a second
run, or a second process, from sending the same message twice. The email
goes first; the SMS — which only tells the guest to look in their inbox —
follows only once the email is out.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from beanie.odm.utils.encoder import Encoder
from markdown_it import MarkdownIt
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.core.notifications import send_html_email, send_sms
from app.models.booking import Booking
from app.models.guest import Guest, Language
from app.models.message_delivery import MessageDelivery
from app.models.message_template import (
    PLACEHOLDER_PATTERN,
    PLACEHOLDERS,
    MessageTemplate,
    MessageTemplateVersion,
)
from app.services import email_templates

logger = logging.getLogger(__name__)

_encoder = Encoder()

FALLBACK_LANGUAGE: Language = "en"
DATE_FORMAT = "%d.%m.%Y"
# Children this age or older count as "older than 6".
CHILD_AGE_THRESHOLD = 6

# CommonMark plus the two GFM extensions the admin editor's preview renders
# (tables, ~~strikethrough~~), with raw HTML switched off.
_markdown = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])

_MARKDOWN_PUNCTUATION = re.compile(r"([\\`*_{}\[\]()#+\-.!|~<>&\"'])")

# Stand-in values for the admin's test send and preview.
SAMPLE_VALUES: dict[str, str] = {
    "guest_first_name": "Anna",
    "guest_last_name": "Muster",
    "checkin_date": "12.11.2026",
    "checkout_date": "16.11.2026",
    "stay_days": "4",
    "adults_number": "2",
    "children_older_6yo_number": "1",
    "children_below_6yo_number": "1",
}


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


# ── Rendering ────────────────────────────────────────────────────────────


def checkin_of(booking: Booking) -> date | None:
    return min((r.begin_date for r in booking.date_ranges), default=None)


def checkout_of(booking: Booking) -> date | None:
    return max((r.end_date for r in booking.date_ranges), default=None)


def placeholder_values(booking: Booking, guest: Guest) -> dict[str, str]:
    """Every placeholder's value for this booking, as display text.

    The guest counts are blank on a booking made before they were recorded
    (`adults` is None) rather than a misleading "0".
    """
    checkin, checkout = checkin_of(booking), checkout_of(booking)
    has_counts = booking.adults is not None
    return {
        "guest_first_name": guest.first_name,
        "guest_last_name": guest.family_name,
        "checkin_date": checkin.strftime(DATE_FORMAT) if checkin else "",
        "checkout_date": checkout.strftime(DATE_FORMAT) if checkout else "",
        "stay_days": str((checkout - checkin).days) if checkin and checkout else "",
        "adults_number": str(booking.adults) if has_counts else "",
        "children_older_6yo_number": (
            str(sum(1 for age in booking.children_ages if age >= CHILD_AGE_THRESHOLD)) if has_counts else ""
        ),
        "children_below_6yo_number": (
            str(sum(1 for age in booking.children_ages if age < CHILD_AGE_THRESHOLD)) if has_counts else ""
        ),
    }


def substitute(text: str, values: dict[str, str], *, escape_markdown: bool = False) -> str:
    """Replace each known `{{name}}` in `text`. Unknown names are left as
    they are — the template validator refuses them, so one can only reach
    here from a stored document that predates a placeholder's removal."""

    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name not in PLACEHOLDERS:
            return match.group(0)
        value = values.get(name, "")
        return _MARKDOWN_PUNCTUATION.sub(r"\\\1", value) if escape_markdown else value

    return PLACEHOLDER_PATTERN.sub(replace, text)


@dataclass
class RenderedMessage:
    subject: str
    html: str


def render_message(version: MessageTemplateVersion, values: dict[str, str]) -> RenderedMessage:
    subject = substitute(version.subject, values)
    body_html = _markdown.render(substitute(version.body_markdown, values, escape_markdown=True))
    html = email_templates.render_shared(
        "guest_message.html",
        {"business_name": settings.business_name, "subject": subject, "body_html": body_html},
    )
    return RenderedMessage(subject=subject, html=html)


def pick_version(template: MessageTemplate, preferred: Language | None) -> MessageTemplateVersion | None:
    """The guest's own language if the template has it, else English. None
    when neither exists — that message is skipped for this guest."""
    by_language = {version.language: version for version in template.versions}
    if preferred is not None and preferred in by_language:
        return by_language[preferred]
    return by_language.get(FALLBACK_LANGUAGE)


def render_sms(language: Language | None, subject: str) -> str:
    # The template closes the subject with its own full stop; a subject that
    # already ends a sentence ("Danke, Lena!") would otherwise get two.
    subject = subject.rstrip()
    sentence = subject if subject.endswith((".", "!", "?", "…")) else f"{subject}."
    return email_templates.render_text(
        language=language,
        name="guest_message_sms.txt",
        context={"business_name": settings.business_name, "subject_sentence": sentence},
    ).strip()


# ── Scheduling ───────────────────────────────────────────────────────────

_ANCHOR_FIELDS = {
    "booking_date": "booking_date",
    "checkin": "date_ranges.begin_date",
    "checkout": "date_ranges.end_date",
}


def anchor_of(template: MessageTemplate, booking: Booking) -> date | None:
    if template.anchor == "booking_date":
        return booking.booking_date
    if template.anchor == "checkin":
        return checkin_of(booking)
    return checkout_of(booking)


def send_day_for(template: MessageTemplate, anchor: date) -> date:
    offset = timedelta(days=template.offset_days)
    return anchor + offset if template.direction == "after" else anchor - offset


def anchor_for_send_day(template: MessageTemplate, send_day: date) -> date:
    offset = timedelta(days=template.offset_days)
    return send_day - offset if template.direction == "after" else send_day + offset


def send_window(template: MessageTemplate, today: date) -> list[date]:
    """The days a run on `today` still sends this template for, oldest first."""
    first = max(today - timedelta(days=settings.guest_message_catch_up_days), template.created_at.date())
    return [first + timedelta(days=i) for i in range((today - first).days + 1)]


async def due_bookings(template: MessageTemplate, today: date) -> list[tuple[Booking, date]]:
    """(booking, day it fell due) for every Active booking this template is
    due for in the window ending `today`."""
    window = send_window(template, today)
    if not window:
        return []
    anchors = [anchor_for_send_day(template, day) for day in window]
    # The query matches any range of a multi-range stay; whether the match
    # is the stay's actual check-in/check-out is decided below.
    candidates = await Booking.find(
        {"status": "Active", _ANCHOR_FIELDS[template.anchor]: {"$in": [_encoder.encode(a) for a in anchors]}}
    ).to_list()
    due: list[tuple[Booking, date]] = []
    for booking in candidates:
        anchor = anchor_of(template, booking)
        if anchor is None:
            continue
        send_day = send_day_for(template, anchor)
        if send_day in window and send_day >= booking.booking_date:
            due.append((booking, send_day))
    return due


# ── Sending ──────────────────────────────────────────────────────────────


async def _claim(template: MessageTemplate, booking: Booking, send_day: date) -> MessageDelivery | None:
    """The delivery row this run may send, or None if it must not.

    A new row is claimed by inserting it. An existing one is only taken up
    again when its email failed and has attempts left; one that is "pending"
    belongs to a send still in flight (or one that died mid-send — not
    retried, since the email may well have gone out).
    """
    delivery = MessageDelivery(template_id=template.id, booking_id=booking.id, scheduled_for=send_day)
    try:
        await delivery.insert()
        return delivery
    except DuplicateKeyError:
        existing = await MessageDelivery.find_one(
            MessageDelivery.template_id == template.id, MessageDelivery.booking_id == booking.id
        )
        if (
            existing is not None
            and existing.email_status == "failed"
            and existing.attempts < settings.guest_message_max_attempts
        ):
            return existing
        return None


async def deliver(template: MessageTemplate, booking: Booking, send_day: date) -> bool:
    """Send `template` for `booking` unless it already went out. True when
    the email was sent by this call."""
    delivery = await _claim(template, booking, send_day)
    if delivery is None:
        return False

    guest = await booking.resolved_guest()
    if guest is None or guest.is_redacted:
        delivery.email_status = delivery.sms_status = "skipped"
        delivery.email_error = "Guest record no longer available"
        await delivery.save()
        return False

    version = pick_version(template, guest.preferred_language)
    if version is None:
        delivery.email_status = delivery.sms_status = "skipped"
        delivery.email_error = f"No {guest.preferred_language or FALLBACK_LANGUAGE} or English version"
        await delivery.save()
        return False

    message = render_message(version, placeholder_values(booking, guest))
    delivery.language = version.language
    delivery.recipient_email = guest.email
    delivery.subject = message.subject
    delivery.attempts += 1
    try:
        await send_html_email(guest.email, message.subject, message.html)
    except Exception as exc:
        logger.exception("Guest message %s failed for booking %s", template.id, booking.id)
        delivery.email_status = "failed"
        delivery.email_error = str(exc) or type(exc).__name__
        await delivery.save()
        return False
    delivery.email_status = "sent"
    delivery.email_error = None
    delivery.sent_at = datetime.now(timezone.utc)

    try:
        await send_sms(guest.phone_number, render_sms(guest.preferred_language, message.subject))
        delivery.sms_status = "sent"
    except Exception as exc:
        # Not retried: the email — the message itself — is out, and a
        # resend would duplicate it.
        logger.exception("Guest message SMS %s failed for booking %s", template.id, booking.id)
        delivery.sms_status = "failed"
        delivery.sms_error = str(exc) or type(exc).__name__
    await delivery.save()
    return True


async def send_due_messages(today: date | None = None) -> int:
    """One pass over every active template. Returns how many emails went out."""
    today = today or utc_today()
    sent = 0
    for template in await MessageTemplate.find(MessageTemplate.active == True).to_list():  # noqa: E712
        for booking, send_day in await due_bookings(template, today):
            try:
                if await deliver(template, booking, send_day):
                    sent += 1
            except Exception:
                # One bad booking must not stop the rest of the pass.
                logger.exception("Guest message %s errored for booking %s", template.id, booking.id)
    return sent


async def send_test_message(template: MessageTemplate, language: Language, to_address: str) -> RenderedMessage:
    """Render one version with SAMPLE_VALUES and email it to an admin."""
    version = next((v for v in template.versions if v.language == language), None)
    if version is None:
        raise ValueError(f"This message has no {language} version")
    message = render_message(version, SAMPLE_VALUES)
    await send_html_email(to_address, message.subject, message.html)
    return message
