import logging
import smtplib
from email.message import EmailMessage
from email.headerregistry import Address

from twilio.rest import Client as TwilioClient

from app.core.config import settings

logger = logging.getLogger("app.notifications")


def send_otp_email(to_address: str, code: str) -> None:
    if not settings.smtp_host:
        logger.info("OTP email (SMTP not configured, logging instead) to=%s code=%s", to_address, code)
        return

    message = EmailMessage()
    message["Subject"] = "Your Berg See Home verification code"
    message["From"] = Address(addr_spec=settings.smtp_from_address)
    message["To"] = Address(addr_spec=to_address)
    message.set_content(f"Your verification code is {code}. It expires in a few minutes.")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)


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
    )
