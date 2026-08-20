from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.api.common import get_or_404, normalize_phone_or_400
from app.api.deps import (
    Principal,
    ensure_can_access_guest,
    get_current_principal,
    require_admin,
    require_pending_guest,
)
from app.core.identifiers import classify_identifier, normalize_identifier
from app.core.security import create_access_token
from app.models.guest import Guest
from app.schemas.guest import GuestCreate, GuestCreateResponse, GuestSelfRegistration, GuestSelfRegistrationResponse

router = APIRouter(prefix="/guests", tags=["guests"])


def _normalize_email(raw: str) -> str:
    return normalize_identifier(raw, "email")


_EMAIL_IN_USE = "Email already in use"
_PHONE_IN_USE = "Phone number already in use"


async def _ensure_unique_contact(
    email: str, phone_number: str, *, exclude_id: PydanticObjectId | None = None
) -> None:
    """Pre-flight check that produces a helpful, field-specific 409.

    One $or query rather than two sequential lookups. This is *not* the
    enforcement mechanism — it can't be, since two simultaneous
    registrations would both pass it; the unique indexes on guests.email and
    guests.phone_number are, and _insert_guest below turns the resulting
    DuplicateKeyError into the same 409.
    """
    query: dict = {"$or": [{"email": email}, {"phone_number": phone_number}]}
    if exclude_id is not None:
        query["_id"] = {"$ne": exclude_id}
    conflict = await Guest.find_one(query)
    if conflict is None:
        return
    # Email first, matching the order these used to be checked in, so a
    # record clashing on both still reports the email.
    detail = _EMAIL_IN_USE if conflict.email == email else _PHONE_IN_USE
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


async def _insert_guest(guest: Guest) -> Guest:
    """Insert, translating a unique-index violation into the same 409 the
    pre-check raises. This is what actually closes the check-then-write race
    between two concurrent registrations for the same address."""
    try:
        await guest.insert()
    except DuplicateKeyError as exc:
        key = (exc.details or {}).get("keyPattern") or {}
        detail = _PHONE_IN_USE if "phone_number" in key else _EMAIL_IN_USE
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
    return guest


@router.post(
    "", response_model=GuestCreateResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)]
)
async def create_guest(payload: GuestCreate) -> GuestCreateResponse:
    data = payload.model_dump()
    data["phone_number"] = normalize_phone_or_400(data["phone_number"])
    data["email"] = _normalize_email(data["email"])
    await _ensure_unique_contact(data["email"], data["phone_number"])
    guest = await _insert_guest(Guest(**data))
    access_token, expires_in = create_access_token(str(guest.id), "guest")
    return GuestCreateResponse(guest=guest, access_token=access_token, expires_in=expires_in)


@router.post("/self", response_model=GuestSelfRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register_guest_self(
    payload: GuestSelfRegistration, principal: Principal = Depends(require_pending_guest)
) -> GuestSelfRegistrationResponse:
    """Complete registration for a first-time guest after OTP verification.

    The verified identifier (from the pending_guest token) fills the
    corresponding email/phone field; the client cannot override it.
    """
    kind = classify_identifier(principal.identifier)
    identifier = normalize_identifier(principal.identifier, kind)

    data = payload.model_dump(exclude={"email", "phone_number"})
    if kind == "email":
        if not payload.phone_number:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="phone_number is required")
        data["email"] = identifier
        data["phone_number"] = normalize_phone_or_400(payload.phone_number)
    else:
        if not payload.email:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="email is required")
        data["phone_number"] = identifier
        data["email"] = _normalize_email(payload.email)

    await _ensure_unique_contact(data["email"], data["phone_number"])

    guest = await _insert_guest(Guest(**data))

    access_token, expires_in = create_access_token(str(guest.id), "guest")
    return GuestSelfRegistrationResponse(guest=guest, access_token=access_token, expires_in=expires_in)


@router.get("", response_model=list[Guest], dependencies=[Depends(require_admin)])
async def list_guests() -> list[Guest]:
    return await Guest.find_all().to_list()


@router.get("/{guest_id}", response_model=Guest)
async def get_guest(guest_id: PydanticObjectId, principal: Principal = Depends(get_current_principal)) -> Guest:
    ensure_can_access_guest(principal, guest_id)
    return await get_or_404(Guest, guest_id, "Guest")


@router.put("/{guest_id}", response_model=Guest)
async def update_guest(
    guest_id: PydanticObjectId, payload: GuestCreate, principal: Principal = Depends(get_current_principal)
) -> Guest:
    ensure_can_access_guest(principal, guest_id)
    guest = await get_or_404(Guest, guest_id, "Guest")
    phone_number = normalize_phone_or_400(payload.phone_number)
    email = _normalize_email(payload.email)
    await _ensure_unique_contact(email, phone_number, exclude_id=guest_id)
    guest.family_name = payload.family_name
    guest.first_name = payload.first_name
    guest.residence_address = payload.residence_address
    guest.phone_number = phone_number
    guest.email = email
    guest.preferred_language = payload.preferred_language
    guest.preferred_currency = payload.preferred_currency
    await guest.save()
    return guest


@router.delete("/{guest_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
async def delete_guest(guest_id: PydanticObjectId) -> None:
    guest = await get_or_404(Guest, guest_id, "Guest")
    await guest.delete()
