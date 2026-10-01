"""Outbound email (SendGrid) and SMS (Twilio) delivery.

Both vendor clients are synchronous and make blocking HTTPS calls, so every
send below is pushed onto a worker thread rather than run on the event loop
— same reasoning (and same mechanism) as app.services.stripe_service.
Without this, a single OTP request stalls every other request the worker is
serving for the duration of the round trip.

On preprod every message is visibly marked as a test (see _mark_* below), so
a preprod booking or OTP can never be mistaken for a real one. The marking
happens here, at the single choke point every email and SMS passes through,
rather than in the templates — production output is left byte-for-byte as
the templates render it.
"""

import asyncio
import base64
import html
import logging
import re
from dataclasses import dataclass
from functools import partial

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Attachment,
    Content,
    ContentId,
    Disposition,
    Email,
    FileContent,
    FileName,
    FileType,
    Mail,
    To,
)
from twilio.rest import Client as TwilioClient
from twilio.rest.api.v2010.account.message import MessageInstance

from app.core.config import settings

logger = logging.getLogger("app.notifications")


TEST_PREFIX = "[TEST MESSAGE]"
TEST_BANNER = "[THIS IS A TEST MESSAGE]"
_TEST_BANNER_HTML = (
    f'<p style="color:#d00000; font-weight:bold; margin:0 0 16px 0;">'
    f"<strong>{html.escape(TEST_BANNER)}</strong></p>"
)
_BODY_OPEN_TAG = re.compile(r"<body\b[^>]*>", re.IGNORECASE)


def _is_test_environment() -> bool:
    return settings.environment == "preprod"


def _mark_subject(subject: str) -> str:
    return f"{TEST_PREFIX} {subject}" if _is_test_environment() else subject


def _mark_text_body(text_content: str) -> str:
    # Plain-text mail can't carry colour or weight; the banner line is the
    # best a text/plain part can do.
    return f"{TEST_BANNER}\n\n{text_content}" if _is_test_environment() else text_content


def _mark_html_body(html_content: str) -> str:
    """Banner as the first thing inside <body>, or at the very start when the
    document has no <body> tag."""
    if not _is_test_environment():
        return html_content
    match = _BODY_OPEN_TAG.search(html_content)
    if match is None:
        return _TEST_BANNER_HTML + html_content
    return html_content[: match.end()] + _TEST_BANNER_HTML + html_content[match.end() :]


def _mark_sms(body: str) -> str:
    return f"{TEST_PREFIX} {body}" if _is_test_environment() else body


@dataclass
class EmailAttachment:
    filename: str
    content: bytes
    mime_type: str
    # Set for an inline image: the HTML body shows it with
    # <img src="cid:{content_id}"> instead of listing it as a download.
    content_id: str | None = None


async def send_text_email(to_address: str, subject: str, text_content: str) -> None:
    subject = _mark_subject(subject)
    text_content = _mark_text_body(text_content)
    if not settings.sendgrid_api_key:
        logger.info(
            "Email (SendGrid not configured, logging instead) to=%s subject=%s body=%s",
            to_address,
            subject,
            text_content,
        )
        return

    from_email = Email(settings.sendgrid_from_address)
    to_email = To(to_address)
    content = Content("text/plain", text_content)

    message = Mail(from_email, to_email, subject, content)

    await asyncio.to_thread(SendGridAPIClient(settings.sendgrid_api_key).send, message)


async def send_html_email(
    to_address: str,
    subject: str,
    html_content: str,
    attachments: list[EmailAttachment] | None = None,
) -> None:
    subject = _mark_subject(subject)
    html_content = _mark_html_body(html_content)
    if not settings.sendgrid_api_key:
        logger.info(
            "Email (SendGrid not configured, logging instead) to=%s subject=%s attachments=%s",
            to_address,
            subject,
            [a.filename for a in attachments or []],
        )
        return

    from_email = Email(settings.sendgrid_from_address, settings.business_name)
    to_email = To(to_address)
    content = Content("text/html", html_content)
    message = Mail(from_email, to_email, subject, content)
    for attachment in attachments or []:
        message.add_attachment(
            Attachment(
                FileContent(base64.b64encode(attachment.content).decode()),
                FileName(attachment.filename),
                FileType(attachment.mime_type),
                Disposition("inline" if attachment.content_id else "attachment"),
                ContentId(attachment.content_id) if attachment.content_id else None,
            )
        )

    await asyncio.to_thread(SendGridAPIClient(settings.sendgrid_api_key).send, message)


async def send_sms(to_number: str, body: str) -> None:
    body = _mark_sms(body)
    if not (
        settings.twilio_account_sid
        and settings.twilio_auth_token
        and settings.twilio_messaging_service_sid
    ):
        logger.info("SMS (Twilio not configured, logging instead) to=%s body=%s", to_number, body)
        return

    client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
    await asyncio.to_thread(
        partial(
            client.messages.create,
            to=to_number,
            messaging_service_sid=settings.twilio_messaging_service_sid,
            body=body,
            risk_check=MessageInstance.RiskCheck.DISABLE,
        )
    )
