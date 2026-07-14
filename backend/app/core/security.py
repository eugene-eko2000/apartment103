import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt

from app.core.config import settings

SubjectType = Literal["guest", "admin", "pending_guest"]


def generate_otp_code() -> str:
    upper_bound = 10**settings.otp_length
    return str(secrets.randbelow(upper_bound)).zfill(settings.otp_length)


def hash_otp_code(identifier: str, code: str) -> str:
    # Salting with the identifier keeps precomputed rainbow tables useless
    # without needing a per-challenge salt column.
    return hashlib.sha256(f"{identifier}:{code}".encode()).hexdigest()


def verify_otp_code(identifier: str, code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_otp_code(identifier, code), code_hash)


def create_access_token(subject_id: str, subject_type: SubjectType) -> tuple[str, int]:
    expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    expires_at = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": subject_id,
        "type": subject_type,
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
