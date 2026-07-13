from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import Principal, get_current_principal, require_admin
from app.models.guest import Guest
from app.schemas.guest import GuestCreate

router = APIRouter(prefix="/guests", tags=["guests"])


def _ensure_can_access_guest(principal: Principal, guest_id: PydanticObjectId) -> None:
    if not principal.is_admin and not principal.owns_guest(guest_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this guest")


@router.post("", response_model=Guest, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
async def create_guest(payload: GuestCreate) -> Guest:
    guest = Guest(**payload.model_dump())
    await guest.insert()
    return guest


@router.get("", response_model=list[Guest], dependencies=[Depends(require_admin)])
async def list_guests() -> list[Guest]:
    return await Guest.find_all().to_list()


@router.get("/{guest_id}", response_model=Guest)
async def get_guest(guest_id: PydanticObjectId, principal: Principal = Depends(get_current_principal)) -> Guest:
    _ensure_can_access_guest(principal, guest_id)
    guest = await Guest.get(guest_id)
    if guest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guest not found")
    return guest


@router.put("/{guest_id}", response_model=Guest)
async def update_guest(
    guest_id: PydanticObjectId, payload: GuestCreate, principal: Principal = Depends(get_current_principal)
) -> Guest:
    _ensure_can_access_guest(principal, guest_id)
    guest = await Guest.get(guest_id)
    if guest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guest not found")
    guest.family_name = payload.family_name
    guest.first_name = payload.first_name
    guest.residence_address = payload.residence_address
    guest.phone_number = payload.phone_number
    guest.email = payload.email
    guest.preferred_language = payload.preferred_language
    guest.preferred_currency = payload.preferred_currency
    await guest.save()
    return guest


@router.delete("/{guest_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
async def delete_guest(guest_id: PydanticObjectId) -> None:
    guest = await Guest.get(guest_id)
    if guest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guest not found")
    await guest.delete()
