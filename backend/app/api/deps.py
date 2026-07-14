from dataclasses import dataclass

import jwt
from beanie import PydanticObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import SubjectType, decode_access_token
from app.models.admin import Admin
from app.models.guest import Guest

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    type: SubjectType
    id: PydanticObjectId | None = None
    guest: Guest | None = None
    admin: Admin | None = None
    # Verified email/phone number, set only for a "pending_guest" principal
    # (i.e. an OTP was verified for an identifier with no Guest record yet).
    identifier: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.type == "admin"

    @property
    def is_guest(self) -> bool:
        return self.type == "guest"

    @property
    def is_pending_guest(self) -> bool:
        return self.type == "pending_guest"

    def owns_guest(self, guest_id: PydanticObjectId) -> bool:
        return self.is_guest and self.id == guest_id


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> Principal:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise unauthorized from exc

    subject_type: SubjectType = claims.get("type")
    subject_id = claims.get("sub")
    if subject_type not in ("guest", "admin", "pending_guest") or subject_id is None:
        raise unauthorized

    if subject_type == "pending_guest":
        return Principal(type="pending_guest", identifier=subject_id)

    try:
        object_id = PydanticObjectId(subject_id)
    except Exception as exc:
        raise unauthorized from exc

    if subject_type == "admin":
        admin = await Admin.get(object_id)
        if admin is None:
            raise unauthorized
        return Principal(type="admin", id=object_id, admin=admin)

    guest = await Guest.get(object_id)
    if guest is None:
        raise unauthorized
    return Principal(type="guest", id=object_id, guest=guest)


async def require_admin(principal: Principal = Depends(get_current_principal)) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return principal


async def require_pending_guest(principal: Principal = Depends(get_current_principal)) -> Principal:
    if not principal.is_pending_guest:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="A verified but unregistered identifier is required"
        )
    return principal
