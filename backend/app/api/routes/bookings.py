from beanie import Link, PydanticObjectId
from beanie.operators import In
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import Principal, get_current_principal
from app.models.booking import Booking, BookingCancellationPolicy, BookingDateRange
from app.models.cancellation_policy import CancellationPolicy
from app.models.guest import Currency, Guest
from app.schemas.booking import (
    BookedDateRange,
    BookingChargeDisplay,
    BookingCreate,
    BookingDateRangeInput,
    BookingDisplay,
    BookingRangeDisplay,
    BookingScheduleDisplay,
)
from app.services.charge_schedule import build_charge_schedule
from app.services.currency_service import convert_amount
from app.services.payment_reconciliation import settle_cancellation

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


async def _get_pending_booking_for_guest(guest_id: PydanticObjectId) -> Booking | None:
    return await Booking.find_one({"guest.$id": guest_id, "status": "Pending"})


def _snapshot_cancellation_policy(policy: CancellationPolicy) -> BookingCancellationPolicy:
    return BookingCancellationPolicy(name=policy.name, rules=policy.rules)


def _booking_guest_id(booking: Booking) -> PydanticObjectId:
    return booking.guest.ref.id if isinstance(booking.guest, Link) else booking.guest.id


def _ensure_can_access_booking(principal: Principal, booking: Booking) -> None:
    if not principal.is_admin and _booking_guest_id(booking) != principal.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this booking")


async def _date_ranges_in_currency(
    date_ranges: list[BookingDateRangeInput], currency: Currency
) -> list[BookingDateRange]:
    """Resolves each input range's stored `price`: if `price_chf` is set
    (the booking widget's guest flow), it's converted to `currency` here —
    the one place a booking's authoritative charge amount is produced from a
    CHF figure. Otherwise `price` is used exactly as given (the admin
    editor's manual-override flow), untouched by currency conversion."""
    return [
        BookingDateRange(
            begin_date=date_range.begin_date,
            end_date=date_range.end_date,
            price=(
                await convert_amount(date_range.price_chf, "CHF", currency)
                if date_range.price_chf is not None
                else date_range.price
            ),
        )
        for date_range in date_ranges
    ]


async def _build_display(booking: Booking, currency: Currency) -> BookingDisplay:
    """Currency-converted view of `booking`'s money fields — computed on
    demand, never persisted. Powers GET /bookings/{id}/display and
    GET /bookings/display; never used by the admin-facing plain Booking
    endpoints, which always show raw, un-converted figures."""
    date_ranges = [
        BookingRangeDisplay(
            price=await convert_amount(r.price, booking.currency, currency),
            price_chf=await convert_amount(r.price, booking.currency, "CHF"),
        )
        for r in booking.date_ranges
    ]
    charges = [
        BookingChargeDisplay(
            amount=await convert_amount(c.amount, c.currency, currency),
            amount_chf=await convert_amount(c.amount, c.currency, "CHF"),
        )
        for c in booking.charges
    ]
    charge_schedule = [
        BookingScheduleDisplay(
            amount=await convert_amount(e.amount, booking.currency, currency),
            amount_chf=await convert_amount(e.amount, booking.currency, "CHF"),
        )
        for e in booking.charge_schedule
    ]
    return BookingDisplay(
        currency=currency,
        total_price=await convert_amount(booking.total_price, booking.currency, currency),
        total_price_chf=await convert_amount(booking.total_price, booking.currency, "CHF"),
        date_ranges=date_ranges,
        charges=charges,
        charge_schedule=charge_schedule,
    )


@router.post("", response_model=Booking, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: BookingCreate, principal: Principal = Depends(get_current_principal)
) -> Booking:
    if not principal.is_admin and payload.guest_id != principal.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Guests may only book for themselves")
    guest = await _get_guest_or_404(payload.guest_id)
    # Only one Pending booking per guest at a time — a returning guest with
    # one already stored is meant to resume straight into paying for it
    # (see the frontend's post-login lookup) rather than start another.
    if await _get_pending_booking_for_guest(guest.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a pending booking. Complete or cancel it before starting a new one.",
        )
    cancellation_policy = await _get_cancellation_policy_or_404(payload.cancellation_policy_id)
    booking = Booking(
        guest=guest,
        currency=payload.currency,
        date_ranges=await _date_ranges_in_currency(payload.date_ranges, payload.currency),
        cancellation_policy=_snapshot_cancellation_policy(cancellation_policy),
    )
    booking.charge_schedule = build_charge_schedule(booking)
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


# Registered before "/{booking_id}" so the literal "display" path segment
# isn't swallowed by that route's PydanticObjectId path param.
@router.get("/display", response_model=dict[str, BookingDisplay])
async def list_bookings_display(
    currency: Currency, principal: Principal = Depends(get_current_principal)
) -> dict[str, BookingDisplay]:
    if principal.is_admin:
        bookings = await Booking.find_all().to_list()
    else:
        bookings = await Booking.find({"guest.$id": principal.id}).to_list()
    return {str(booking.id): await _build_display(booking, currency) for booking in bookings}


@router.get("/{booking_id}", response_model=Booking)
async def get_booking(
    booking_id: PydanticObjectId, principal: Principal = Depends(get_current_principal)
) -> Booking:
    booking = await Booking.get(booking_id, fetch_links=True)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    _ensure_can_access_booking(principal, booking)
    return booking


@router.get("/{booking_id}/display", response_model=BookingDisplay)
async def get_booking_display(
    booking_id: PydanticObjectId, currency: Currency, principal: Principal = Depends(get_current_principal)
) -> BookingDisplay:
    booking = await Booking.get(booking_id)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    _ensure_can_access_booking(principal, booking)
    return await _build_display(booking, currency)


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
    await settle_cancellation(booking)
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
    booking.date_ranges = await _date_ranges_in_currency(payload.date_ranges, payload.currency)
    booking.cancellation_policy = _snapshot_cancellation_policy(cancellation_policy)
    booking.charge_schedule = build_charge_schedule(booking)
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
    # A guest can only outright delete a still-Pending booking (e.g.
    # cancelling out of checkout before paying) — an Active/Cancelled one
    # has payment/audit history and must go through /cancel instead. Admins
    # keep unrestricted delete for cleanup.
    if not principal.is_admin and booking.status != "Pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only a pending booking can be deleted directly; cancel it instead.",
        )
    await booking.delete()
