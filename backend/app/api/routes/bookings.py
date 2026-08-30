from datetime import datetime, timezone
from decimal import Decimal

from beanie import PydanticObjectId
from beanie.operators import In
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.api.common import ensure_guest_not_redacted, get_or_404
from app.api.deps import (
    Principal,
    ensure_can_access_booking,
    get_current_principal,
)
from app.models.booking import (
    Booking,
    BookingCancellationPolicy,
    BookingDateRange,
    nights_of_ranges,
)
from app.models.cancellation_policy import CancellationPolicy
from app.models.guest import Currency, Guest
from app.models.plan import Plan
from app.schemas.booking import (
    BookedDateRange,
    BookingChargeDisplay,
    BookingCreate,
    BookingDateRangesProjection,
    BookingDisplay,
    BookingDisplaySource,
    BookingRangeDisplay,
    BookingScheduleDisplay,
)
from app.services.availability import (
    BLOCKING_STATUSES,
    DATES_TAKEN_MESSAGE,
    dates_taken_detail,
    expire_pending_bookings,
    find_overlapping_ranges,
    pending_deadline,
)
from app.services.booking_pricing import UnpricedDatesError, price_date_ranges
from app.services.charge_schedule import build_charge_schedule
from app.services.currency_service import convert_amount_with_rates, rates_for
from app.services.payment_reconciliation import settle_cancellation

router = APIRouter(prefix="/bookings", tags=["bookings"])

# Server-side bookkeeping that backs the unique booked_nights index — derived
# entirely from date_ranges, and of no use to any client. Stripped from every
# Booking response rather than hidden on the model, since Beanie's encoder
# honours Field(exclude=True) and would stop persisting it.
_INTERNAL_FIELDS = {"booked_nights"}

# Unauthenticated: lets the booking widget disable already-booked days in the
# calendar without a guest/admin session. Mounted ahead of `router` in
# main.py so "/bookings/public/..." is matched before "/bookings/{booking_id}".
public_router = APIRouter(prefix="/bookings", tags=["bookings"])


@public_router.get("/public/date-ranges", response_model=list[BookedDateRange])
async def list_public_booked_date_ranges() -> list[BookedDateRange]:
    """Every stay currently holding dates, for the calendar's greyed-out
    days.

    Pending bookings are included: a guest in checkout holds their nights
    (see app.services.availability), so showing those days as free would
    only walk the next guest into a conflict they can't get past. Lapsed
    holds are cleared first, so a checkout that ran out of time doesn't grey
    out dates that are in fact free.
    """
    await expire_pending_bookings()
    # Projected to `date_ranges` only: this is anonymous and hit on every
    # calendar open, so it must not drag whole Booking documents (charges,
    # charge_schedule, webhook_events) across the wire to return two dates.
    bookings = await Booking.find(
        {"status": {"$in": BLOCKING_STATUSES}}, projection_model=BookingDateRangesProjection
    ).to_list()
    return [date_range for booking in bookings for date_range in booking.date_ranges]


async def _get_pending_booking_for_guest(guest_id: PydanticObjectId) -> Booking | None:
    # Lapsed holds first: a guest whose previous checkout timed out is
    # starting a fresh booking, not resuming a dead one.
    await expire_pending_bookings()
    return await Booking.find_one({"guest.$id": guest_id, "status": "Pending"})


def _snapshot_cancellation_policy(policy: CancellationPolicy) -> BookingCancellationPolicy:
    return BookingCancellationPolicy(name=policy.name, rules=policy.rules)


async def _resolve_terms(
    payload: BookingCreate, principal: Principal
) -> tuple[list[BookingDateRange], CancellationPolicy]:
    """The date ranges (priced) and cancellation policy a booking is stored
    with — both resolved from the database, never taken on the client's word.

    Two mutually exclusive paths, matching BookingCreate's two shapes:

    * `plan_name` (the guest flow): the named Plan supplies the price ratio
      and, through its link, the policy to snapshot. Prices are computed
      from stored nightly rates by booking_pricing.price_date_ranges — any
      `price` in the payload is discarded. Deriving *both* from the one plan
      is deliberate: it leaves no way to combine a cheap plan's ratio with
      another plan's more lenient cancellation terms.
    * `cancellation_policy_id` (the admin editor): prices are taken from the
      payload verbatim, as a manual override. Admin-only — for a guest
      principal this is exactly the "name your own price" hole the plan path
      exists to close, so it is refused rather than silently repriced.
    """
    if payload.plan_name is not None:
        plan = await Plan.find_one(Plan.name == payload.plan_name, fetch_links=True)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
        # fetch_links leaves a dangling reference as an unresolved Link
        # rather than raising, and a booking must not be written with a
        # half-resolved policy snapshot.
        if not isinstance(plan.cancellation_policy, CancellationPolicy):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This plan's cancellation policy is missing",
            )
        try:
            date_ranges = await price_date_ranges(payload.date_ranges, plan, payload.currency)
        except UnpricedDatesError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return date_ranges, plan.cancellation_policy

    if not principal.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A plan must be chosen for the booking",
        )
    if payload.cancellation_policy_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either plan_name or cancellation_policy_id is required",
        )
    policy = await get_or_404(CancellationPolicy, payload.cancellation_policy_id, "Cancellation policy")
    # An admin typing a final amount is stating the actual figure,
    # promotions included — so there is no discount to record: the regular
    # price *is* the price, and no promotion snapshot applies.
    date_ranges = [
        BookingDateRange(
            begin_date=date_range.begin_date,
            end_date=date_range.end_date,
            price=date_range.price,
            regular_price=date_range.price,
            applied_promotions=[],
        )
        for date_range in payload.date_ranges
    ]
    return date_ranges, policy


async def _build_display(booking: Booking | BookingDisplaySource, currency: Currency) -> BookingDisplay:
    """Currency-converted view of `booking`'s money fields — computed on
    demand, never persisted. Powers GET /bookings/{id}/display and
    GET /bookings/display; never used by the admin-facing plain Booking
    endpoints, which always show raw, un-converted figures.

    Rates are fetched once and every amount converted against that one
    snapshot: a booking has upwards of a dozen money fields, and awaiting a
    coroutine per field (times every booking, for the list endpoint) is pure
    overhead once the arithmetic itself is synchronous.
    """
    rates = await rates_for({booking.currency, *(c.currency for c in booking.charges)}, currency, "CHF")

    def convert(amount, from_currency) -> Decimal:
        return convert_amount_with_rates(amount, from_currency, currency, rates)

    def convert_chf(amount, from_currency) -> Decimal:
        return convert_amount_with_rates(amount, from_currency, "CHF", rates)

    return BookingDisplay(
        currency=currency,
        total_price=convert(booking.total_price, booking.currency),
        total_price_chf=convert_chf(booking.total_price, booking.currency),
        total_regular_price=convert(booking.total_regular_price, booking.currency),
        total_regular_price_chf=convert_chf(booking.total_regular_price, booking.currency),
        total_discount=convert(booking.total_discount, booking.currency),
        date_ranges=[
            BookingRangeDisplay(
                price=convert(r.price, booking.currency),
                price_chf=convert_chf(r.price, booking.currency),
                regular_price=convert(r.regular_price, booking.currency),
                regular_price_chf=convert_chf(r.regular_price, booking.currency),
                discount=convert(r.regular_price - r.price, booking.currency),
            )
            for r in booking.date_ranges
        ],
        charges=[
            BookingChargeDisplay(amount=convert(c.amount, c.currency), amount_chf=convert_chf(c.amount, c.currency))
            for c in booking.charges
        ],
        charge_schedule=[
            BookingScheduleDisplay(
                amount=convert(e.amount, booking.currency),
                amount_chf=convert_chf(e.amount, booking.currency),
            )
            for e in booking.charge_schedule
        ],
    )


async def _insert_claiming_nights(booking: Booking) -> None:
    """Store a booking, taking its nights with it — or refuse, naming the
    dates that are already spoken for.

    Two checks, and both are needed. `find_overlapping_ranges` is the one
    that can explain itself: it names the conflicting ranges (and covers
    closures, which claim no nights of their own). The unique index on
    booked_nights is the one that cannot be raced: between that query and
    this insert, another guest's checkout may claim the very same nights, and
    only the index sees both writes. So the query answers "why", and the
    index guarantees "at most one".
    """
    overlapping = await find_overlapping_ranges(booking)
    if overlapping:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=dates_taken_detail(overlapping)
        )
    try:
        await booking.insert()
    except DuplicateKeyError as exc:
        # Lost a photo finish. The dates are gone, and there is nothing to
        # name them by — the winning booking landed after the query above —
        # so answer with the same message the guest would have got a
        # millisecond earlier.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=DATES_TAKEN_MESSAGE
        ) from exc


@router.post(
    "",
    response_model=Booking,
    response_model_exclude=_INTERNAL_FIELDS,
    status_code=status.HTTP_201_CREATED,
)
async def create_booking(
    payload: BookingCreate, principal: Principal = Depends(get_current_principal)
) -> Booking:
    if not principal.is_admin and payload.guest_id != principal.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Guests may only book for themselves")
    guest = await get_or_404(Guest, payload.guest_id, "Guest")
    ensure_guest_not_redacted(guest)
    # Only one Pending booking per guest at a time — a returning guest with
    # one already stored is meant to resume straight into paying for it
    # (see the frontend's post-login lookup) rather than start another.
    if await _get_pending_booking_for_guest(guest.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a pending booking. Complete or cancel it before starting a new one.",
        )
    date_ranges, cancellation_policy = await _resolve_terms(payload, principal)
    booking = Booking(
        guest=guest,
        currency=payload.currency,
        date_ranges=date_ranges,
        cancellation_policy=_snapshot_cancellation_policy(cancellation_policy),
        # The booking blocks its dates from this moment, for a limited
        # time — see app.services.availability.
        booked_nights=nights_of_ranges(date_ranges),
        pending_expires_at=pending_deadline(),
    )
    booking.charge_schedule = build_charge_schedule(booking)
    await _insert_claiming_nights(booking)
    return booking


@router.get("", response_model=list[Booking], response_model_exclude={"__all__": _INTERNAL_FIELDS})
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
    # Only the money-bearing fields are needed to build a display (and the
    # non-admin case is already scoped by the query, so no per-document
    # authorization check needs the guest link).
    query = Booking.find_all() if principal.is_admin else Booking.find({"guest.$id": principal.id})
    bookings = await query.project(BookingDisplaySource).to_list()
    return {str(booking.id): await _build_display(booking, currency) for booking in bookings}


@router.get("/{booking_id}", response_model=Booking, response_model_exclude=_INTERNAL_FIELDS)
async def get_booking(
    booking_id: PydanticObjectId, principal: Principal = Depends(get_current_principal)
) -> Booking:
    booking = await get_or_404(Booking, booking_id, "Booking", fetch_links=True)
    ensure_can_access_booking(principal, booking)
    return booking


@router.get("/{booking_id}/display", response_model=BookingDisplay)
async def get_booking_display(
    booking_id: PydanticObjectId, currency: Currency, principal: Principal = Depends(get_current_principal)
) -> BookingDisplay:
    booking = await get_or_404(Booking, booking_id, "Booking")
    ensure_can_access_booking(principal, booking)
    return await _build_display(booking, currency)


@router.post("/{booking_id}/cancel", response_model=Booking, response_model_exclude=_INTERNAL_FIELDS)
async def cancel_booking(
    booking_id: PydanticObjectId, principal: Principal = Depends(get_current_principal)
) -> Booking:
    booking = await get_or_404(Booking, booking_id, "Booking", fetch_links=True)
    ensure_can_access_booking(principal, booking)
    if booking.status == "Cancelled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking is already cancelled")
    await settle_cancellation(booking)
    booking.status = "Cancelled"
    # The cancellation, not the stay's dates, is now the last thing that
    # happened to this booking — it is what the retention sweep counts the
    # guest's month from (see app.services.data_retention).
    booking.cancelled_at = datetime.now(timezone.utc)
    # Release the nights so the dates become bookable again, and drop the
    # Pending deadline with them — there is no hold left to expire.
    booking.booked_nights = []
    booking.pending_expires_at = None
    await booking.save()
    return booking


@router.put("/{booking_id}", response_model=Booking, response_model_exclude=_INTERNAL_FIELDS)
async def update_booking(
    booking_id: PydanticObjectId, payload: BookingCreate, principal: Principal = Depends(get_current_principal)
) -> Booking:
    booking = await get_or_404(Booking, booking_id, "Booking")
    ensure_can_access_booking(principal, booking)
    if not principal.is_admin and payload.guest_id != principal.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Guests may only book for themselves")
    # Only a still-Pending booking is safe to edit in place. Once it has left
    # Pending it carries payment/ledger state — amount_charged, charges, and
    # (for an Active booking) claimed nights — that rebuilding date_ranges,
    # cancellation_policy and charge_schedule would silently invalidate: the
    # edit could leave amount_charged > total_price and a schedule that no
    # longer matches the charges already recorded. Changes to a charged
    # booking have to go through the payment paths (cancel/refund) instead of
    # rewriting money fields here.
    if booking.status != "Pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only a pending booking can be edited",
        )
    guest = await get_or_404(Guest, payload.guest_id, "Guest")
    date_ranges, cancellation_policy = await _resolve_terms(payload, principal)
    booking.guest = guest
    booking.currency = payload.currency
    booking.date_ranges = date_ranges
    booking.cancellation_policy = _snapshot_cancellation_policy(cancellation_policy)
    booking.charge_schedule = build_charge_schedule(booking)
    # Moving the stay means giving up the old nights and claiming the new
    # ones. Same two-step as _insert_claiming_nights: the query names the
    # conflict, the unique index makes the swap safe against a concurrent
    # checkout. The hold is restarted too — the guest is actively working on
    # this booking, and the new dates have only just been taken.
    booking.booked_nights = nights_of_ranges(date_ranges)
    booking.pending_expires_at = pending_deadline()
    overlapping = await find_overlapping_ranges(booking)
    if overlapping:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=dates_taken_detail(overlapping)
        )
    try:
        await booking.save()
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=DATES_TAKEN_MESSAGE
        ) from exc
    return booking


@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_booking(
    booking_id: PydanticObjectId, principal: Principal = Depends(get_current_principal)
) -> None:
    booking = await get_or_404(Booking, booking_id, "Booking")
    ensure_can_access_booking(principal, booking)
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
