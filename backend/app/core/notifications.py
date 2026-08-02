import base64
import logging
from dataclasses import dataclass

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


def send_otp_email(to_address: str, code: str) -> None:
    if not settings.sendgrid_api_key:
        logger.info("OTP email (SendGrid not configured, logging instead) to=%s code=%s", to_address, code)
        return

    from_email = Email(settings.sendgrid_from_address)
    to_email = To(to_address)
    subject = "Your verification code"
    content = Content("text/plain", f"Your verification code is {code}.")

    message = Mail(from_email, to_email, subject, content)

    SendGridAPIClient(settings.sendgrid_api_key).send(message)


def send_html_email(
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

    SendGridAPIClient(settings.sendgrid_api_key).send(message)


def send_otp_sms(to_number: str, code: str) -> None:
    if not (
        settings.twilio_account_sid
        and settings.twilio_auth_token
        and settings.twilio_messaging_service_sid
    ):
        logger.info("OTP SMS (Twilio not configured, logging instead) to=%s code=%s", to_number, code)
        return

    client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
    client.messages.create(
        to=to_number,
        messaging_service_sid=settings.twilio_messaging_service_sid,
        body=f"Your verification code is {code}.",
        risk_check=MessageInstance.RiskCheck.DISABLE,
    )
