"""Outbound email (SendGrid) and SMS (Twilio) delivery.

Both vendor clients are synchronous and make blocking HTTPS calls, so every
send below is pushed onto a worker thread rather than run on the event loop
— same reasoning (and same mechanism) as app.services.stripe_service.
Without this, a single OTP request stalls every other request the worker is
serving for the duration of the round trip.
"""

import asyncio
import base64
import logging
from dataclasses import dataclass
from functools import partial

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Attachment,
    Content,
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


@dataclass
class EmailAttachment:
    filename: str
    content: bytes
    mime_type: str


async def send_text_email(to_address: str, subject: str, text_content: str) -> None:
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
                Disposition("attachment"),
            )
        )

    await asyncio.to_thread(SendGridAPIClient(settings.sendgrid_api_key).send, message)


async def send_sms(to_number: str, body: str) -> None:
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
