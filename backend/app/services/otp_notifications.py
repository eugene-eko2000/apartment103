"""Sends the OTP verification code by email or SMS, in the guest's current
UI language. Wording lives in backend/data/<language>/otp_email.txt and
otp_sms.txt (see app.services.email_templates), not in this module."""

from app.core.notifications import send_sms, send_text_email
from app.models.guest import Language
from app.services import email_templates


async def send_otp_email(to_address: str, code: str, language: Language | None) -> None:
    subject, body = email_templates.render_email(
        language=language, name="otp_email.txt", context={"code": code}
    )
    await send_text_email(to_address, subject, body)


async def send_otp_sms(to_number: str, code: str, language: Language | None) -> None:
    body = email_templates.render_text(language=language, name="otp_sms.txt", context={"code": code})
    await send_sms(to_number, body)
