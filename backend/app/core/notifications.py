import logging

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Content, Email, Mail, To
from twilio.rest import Client as TwilioClient
from twilio.rest.api.v2010.account.message import MessageInstance

from app.core.config import settings

logger = logging.getLogger("app.notifications")


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
