from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, status

from app.models.guest import Guest
from app.schemas.guest import GuestCreate

router = APIRouter(prefix="/guests", tags=["guests"])


@router.post("", response_model=Guest, status_code=status.HTTP_201_CREATED)
async def create_guest(payload: GuestCreate) -> Guest:
    guest = Guest(**payload.model_dump())
    await guest.insert()
    return guest


@router.get("", response_model=list[Guest])
async def list_guests() -> list[Guest]:
    return await Guest.find_all().to_list()


@router.get("/{guest_id}", response_model=Guest)
async def get_guest(guest_id: PydanticObjectId) -> Guest:
    guest = await Guest.get(guest_id)
    if guest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guest not found")
    return guest


@router.put("/{guest_id}", response_model=Guest)
async def update_guest(guest_id: PydanticObjectId, payload: GuestCreate) -> Guest:
    guest = await Guest.get(guest_id)
    if guest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guest not found")
    guest.family_name = payload.family_name
    guest.first_name = payload.first_name
    guest.residence_address = payload.residence_address
    guest.phone_number = payload.phone_number
    guest.preferred_language = payload.preferred_language
    guest.preferred_currency = payload.preferred_currency
    await guest.save()
    return guest


@router.delete("/{guest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_guest(guest_id: PydanticObjectId) -> None:
    guest = await Guest.get(guest_id)
    if guest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guest not found")
    await guest.delete()
