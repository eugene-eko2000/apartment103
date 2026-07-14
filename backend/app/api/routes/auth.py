import re
from datetime import datetime, timedelta, timezone

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.core.identifiers import classify_identifier, normalize_identifier
from app.core.notifications import send_otp_email, send_otp_sms
from app.core.security import (
    SubjectType,
    create_access_token,
    generate_otp_code,
    hash_otp_code,
    verify_otp_code,
)
from app.models.admin import Admin
from app.models.guest import Guest
from app.models.otp_challenge import OtpChallenge
from app.schemas.auth import OtpRequest, OtpVerify, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_OTP_REQUESTED_MESSAGE = "If an account exists for this identifier, a verification code has been sent."


async def _find_principal(identifier: str, kind: str) -> tuple[SubjectType, PydanticObjectId] | None:
    if kind == "email":
        query = {"email": {"$regex": f"^{re.escape(identifier)}$", "$options": "i"}}
    else:
        query = {"phone_number": identifier}

    admin = await Admin.find_one(query)
    if admin is not None:
        return "admin", admin.id

    guest = await Guest.find_one(query)
    if guest is not None:
        return "guest", guest.id

    return None


@router.post("/otp/request", status_code=status.HTTP_202_ACCEPTED)
async def request_otp(payload: OtpRequest) -> dict:
    try:
        kind = classify_identifier(payload.identifier)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    identifier = normalize_identifier(payload.identifier, kind)

    if await _find_principal(identifier, kind) is None:
        # Do not reveal whether the identifier is registered.
        return {"message": _OTP_REQUESTED_MESSAGE}

    last_challenge = (
        await OtpChallenge.find(OtpChallenge.identifier == identifier)
        .sort(-OtpChallenge.created_at)
        .first_or_none()
    )
    now = datetime.now(timezone.utc)
    if last_challenge is not None:
        cooldown_until = last_challenge.created_at + timedelta(
            seconds=settings.otp_resend_cooldown_seconds
        )
        if now < cooldown_until:
            return {"message": _OTP_REQUESTED_MESSAGE}

    code = generate_otp_code()
    challenge = OtpChallenge(
        identifier=identifier,
        channel="email" if kind == "email" else "sms",
        code_hash=hash_otp_code(identifier, code),
        expires_at=now + timedelta(seconds=settings.otp_ttl_seconds),
    )
    await challenge.insert()

    if kind == "email":
        send_otp_email(identifier, code)
    else:
        send_otp_sms(identifier, code)

    return {"message": _OTP_REQUESTED_MESSAGE}


@router.post("/otp/verify", response_model=TokenResponse)
async def verify_otp(payload: OtpVerify) -> TokenResponse:
    try:
        kind = classify_identifier(payload.identifier)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    identifier = normalize_identifier(payload.identifier, kind)
    invalid_code_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired code"
    )

    challenge = (
        await OtpChallenge.find(
            OtpChallenge.identifier == identifier,
            OtpChallenge.consumed_at == None,  # noqa: E711
        )
        .sort(-OtpChallenge.created_at)
        .first_or_none()
    )
    if challenge is None:
        raise invalid_code_error

    now = datetime.now(timezone.utc)
    if now > challenge.expires_at:
        raise invalid_code_error
    if challenge.attempts >= settings.otp_max_attempts:
        raise invalid_code_error

    if not verify_otp_code(identifier, payload.code, challenge.code_hash):
        challenge.attempts += 1
        await challenge.save()
        raise invalid_code_error

    challenge.consumed_at = now
    await challenge.save()

    principal = await _find_principal(identifier, kind)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account found for this identifier")

    subject_type, subject_id = principal
    access_token, expires_in = create_access_token(str(subject_id), subject_type)
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        subject_type=subject_type,
        subject_id=str(subject_id),
    )
