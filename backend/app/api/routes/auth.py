import math
import re
from datetime import datetime, timedelta, timezone

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import Principal, get_current_principal
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
from app.schemas.auth import OtpRequest, OtpRequestResponse, OtpVerify, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_OTP_REQUESTED_MESSAGE = "If an account exists for this identifier, a verification code has been sent."


@router.get("/token/verify")
async def verify_token(principal: Principal = Depends(get_current_principal)) -> dict:
    # get_current_principal already raises 401 for a missing/invalid/expired
    # token, so reaching this point means the bearer token is authenticated.
    return {"status": "OK"}


async def _find_principal(
    identifier: str, kind: str, audience: str
) -> tuple[SubjectType, PydanticObjectId] | None:
    if kind == "email":
        query = {"email": {"$regex": f"^{re.escape(identifier)}$", "$options": "i"}}
    else:
        query = {"phone_number": identifier}

    # Someone can legitimately hold both roles (e.g. staff booking for
    # themselves), so which one wins when an identifier matches both depends
    # on which surface is authenticating: the admin-dashboard login needs
    # "admin" to still resolve to admin, while guest-facing flows (booking,
    # viewing bookings) need "guest" to identify and pre-fill the guest.
    lookups: list[tuple[SubjectType, type[Admin] | type[Guest]]] = [
        ("admin", Admin),
        ("guest", Guest),
    ]
    if audience != "admin":
        lookups.reverse()

    for subject_type, model in lookups:
        match = await model.find_one(query)
        if match is not None:
            return subject_type, match.id

    return None


@router.post("/otp/request", status_code=status.HTTP_202_ACCEPTED, response_model=OtpRequestResponse)
async def request_otp(payload: OtpRequest) -> OtpRequestResponse:
    try:
        kind = classify_identifier(payload.identifier)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    identifier = normalize_identifier(payload.identifier, kind)

    # OTPs are sent for any syntactically valid identifier, registered or
    # not: verifying one is also how a first-time guest starts registration.
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
            retry_after_seconds = math.ceil((cooldown_until - now).total_seconds())
            return OtpRequestResponse(
                message=_OTP_REQUESTED_MESSAGE, retry_after_seconds=retry_after_seconds
            )

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

    return OtpRequestResponse(
        message=_OTP_REQUESTED_MESSAGE, retry_after_seconds=settings.otp_resend_cooldown_seconds
    )


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

    principal = await _find_principal(identifier, kind, payload.audience)
    if principal is None:
        # No Guest/Admin exists for this identifier yet: issue a narrowly
        # scoped token that only lets the client register a new Guest
        # (POST /guests/self) using this verified identifier.
        access_token, expires_in = create_access_token(identifier, "pending_guest")
        return TokenResponse(
            access_token=access_token,
            expires_in=expires_in,
            subject_type="pending_guest",
            subject_id=identifier,
        )

    subject_type, subject_id = principal
    access_token, expires_in = create_access_token(str(subject_id), subject_type)
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        subject_type=subject_type,
        subject_id=str(subject_id),
    )
