from beanie import Link, PydanticObjectId
from beanie.operators import In
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import Principal, get_current_principal
from app.models.booking import Booking, BookingCancellationPolicy
from app.models.cancellation_policy import CancellationPolicy
from app.models.guest import Guest
from app.schemas.booking import BookedDateRange, BookingCreate

router = APIRouter(prefix="/bookings", tags=["bookings"])

# Unauthenticated: lets the booking widget disable already-booked days in the
# calendar without a guest/admin session. Mounted ahead of `router` in
# main.py so "/bookings/public/..." is matched before "/bookings/{booking_id}".
public_router = APIRouter(prefix="/bookings", tags=["bookings"])


@public_router.get("/public/date-ranges", response_model=list[BookedDateRange])
async def list_public_booked_date_ranges() -> list[BookedDateRange]:
    bookings = await Booking.find(Booking.status == "Active").to_list()
    return [
        BookedDateRange(begin_date=date_range.begin_date, end_date=date_range.end_date)
        for booking in bookings
        for date_range in booking.date_ranges
    ]


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


def _booking_guest_id(booking: Booking) -> PydanticObjectId:
    return booking.guest.ref.id if isinstance(booking.guest, Link) else booking.guest.id


def _ensure_can_access_booking(principal: Principal, booking: Booking) -> None:
    if not principal.is_admin and _booking_guest_id(booking) != principal.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this booking")


@router.post("", response_model=Booking, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: BookingCreate, principal: Principal = Depends(get_current_principal)
) -> Booking:
    if not principal.is_admin and payload.guest_id != principal.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Guests may only book for themselves")
    guest = await _get_guest_or_404(payload.guest_id)
    cancellation_policy = await _get_cancellation_policy_or_404(payload.cancellation_policy_id)
    booking = Booking(
        guest=guest,
        currency=payload.currency,
        date_ranges=payload.date_ranges,
        cancellation_policy=_snapshot_cancellation_policy(cancellation_policy),
    )
    await booking.insert()
    return booking


@router.get("", response_model=list[Booking])
async def list_bookings(principal: Principal = Depends(get_current_principal)) -> list[Booking]:
    if principal.is_admin:
        return await Booking.find_all(fetch_links=True).to_list()
    # fetch_links=True runs an aggregation pipeline that reshapes the "guest"
    # field, so a raw "guest.$id" filter can't be applied in the same query.
    # Resolve matching ids first, then re-fetch those with links populated.
    own_booking_ids = [b.id for b in await Booking.find({"guest.$id": principal.id}).to_list()]
    return await Booking.find(In(Booking.id, own_booking_ids), fetch_links=True).to_list()


@router.get("/{booking_id}", response_model=Booking)
async def get_booking(
    booking_id: PydanticObjectId, principal: Principal = Depends(get_current_principal)
) -> Booking:
    booking = await Booking.get(booking_id, fetch_links=True)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    _ensure_can_access_booking(principal, booking)
    return booking


@router.post("/{booking_id}/cancel", response_model=Booking)
async def cancel_booking(
    booking_id: PydanticObjectId, principal: Principal = Depends(get_current_principal)
) -> Booking:
    booking = await Booking.get(booking_id, fetch_links=True)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    _ensure_can_access_booking(principal, booking)
    if booking.status == "Cancelled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking is already cancelled")
    booking.status = "Cancelled"
    await booking.save()
    return booking


@router.put("/{booking_id}", response_model=Booking)
async def update_booking(
    booking_id: PydanticObjectId, payload: BookingCreate, principal: Principal = Depends(get_current_principal)
) -> Booking:
    booking = await Booking.get(booking_id)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    _ensure_can_access_booking(principal, booking)
    if not principal.is_admin and payload.guest_id != principal.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Guests may only book for themselves")
    guest = await _get_guest_or_404(payload.guest_id)
    cancellation_policy = await _get_cancellation_policy_or_404(payload.cancellation_policy_id)
    booking.guest = guest
    booking.currency = payload.currency
    booking.date_ranges = payload.date_ranges
    booking.cancellation_policy = _snapshot_cancellation_policy(cancellation_policy)
    await booking.save()
    return booking


@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_booking(
    booking_id: PydanticObjectId, principal: Principal = Depends(get_current_principal)
) -> None:
    booking = await Booking.get(booking_id)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    _ensure_can_access_booking(booking=booking, principal=principal)
    await booking.delete()
