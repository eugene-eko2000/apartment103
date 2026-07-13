from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, status

from app.models.booking import Booking, BookingCancellationPolicy
from app.models.cancellation_policy import CancellationPolicy
from app.models.guest import Guest
from app.schemas.booking import BookingCreate

router = APIRouter(prefix="/bookings", tags=["bookings"])


async def _get_guest_or_404(guest_id: PydanticObjectId) -> Guest:
    guest = await Guest.get(guest_id)
    if guest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guest not found")
    return guest


async def _get_cancellation_policy_or_404(policy_id: PydanticObjectId) -> CancellationPolicy:
    policy = await CancellationPolicy.get(policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cancellation policy not found")
    return policy


def _snapshot_cancellation_policy(policy: CancellationPolicy) -> BookingCancellationPolicy:
    return BookingCancellationPolicy(name=policy.name, rules=policy.rules)


@router.post("", response_model=Booking, status_code=status.HTTP_201_CREATED)
async def create_booking(payload: BookingCreate) -> Booking:
    guest = await _get_guest_or_404(payload.guest_id)
    cancellation_policy = await _get_cancellation_policy_or_404(payload.cancellation_policy_id)
    booking = Booking(
        guest=guest,
        date_ranges=payload.date_ranges,
        cancellation_policy=_snapshot_cancellation_policy(cancellation_policy),
    )
    await booking.insert()
    return booking


@router.get("", response_model=list[Booking])
async def list_bookings() -> list[Booking]:
    return await Booking.find_all(fetch_links=True).to_list()


@router.get("/{booking_id}", response_model=Booking)
async def get_booking(booking_id: PydanticObjectId) -> Booking:
    booking = await Booking.get(booking_id, fetch_links=True)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    return booking


@router.put("/{booking_id}", response_model=Booking)
async def update_booking(booking_id: PydanticObjectId, payload: BookingCreate) -> Booking:
    booking = await Booking.get(booking_id)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    guest = await _get_guest_or_404(payload.guest_id)
    cancellation_policy = await _get_cancellation_policy_or_404(payload.cancellation_policy_id)
    booking.guest = guest
    booking.date_ranges = payload.date_ranges
    booking.cancellation_policy = _snapshot_cancellation_policy(cancellation_policy)
    await booking.save()
    return booking


@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_booking(booking_id: PydanticObjectId) -> None:
    booking = await Booking.get(booking_id)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    await booking.delete()
