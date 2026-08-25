"""Pricing for a booking that doesn't exist yet.

The booking widget used to multiply a nightly rate by a plan ratio and a
night count in the browser. With promotions that arithmetic is no longer
expressible on the client — the discount depends on which nights a stay
overlaps, on a minimum stay, and on comparing several offers in CHF — and it
should never have been there anyway: a quote the guest sees has to be the
same number the server will charge.

So both endpoints here answer with finished figures, computed by the very
same app.services.booking_pricing.quote_ranges that prices the booking
itself moments later.
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status

from app.core.money import to_decimal
from app.models.guest import Currency
from app.models.plan import Plan
from app.schemas.booking import BookingDateRangeInput
from app.schemas.quote import FromPriceQuote, PlanQuote, QuotePromotion, StayQuote
from app.services.booking_pricing import (
    UnpricedDatesError,
    best_promotion_overlapping,
    load_pricing_snapshot,
    match_min_stay,
    plan_ratio,
    quote_ranges_with,
)
from app.services.currency_service import convert_amount_with_rates

# Unauthenticated by design: this is the price list the booking widget shows
# before anyone has identified themselves. It reveals nothing a guest can't
# already derive from /prices/public and /promotions/public — it just does
# the arithmetic where the arithmetic belongs.
public_router = APIRouter(prefix="/quotes", tags=["quotes"])


def _per_night(total: Decimal, nights: int) -> Decimal:
    return to_decimal(total / nights) if nights > 0 else to_decimal(total)


@public_router.get("/public", response_model=StayQuote)
async def get_stay_quote(begin_date: date, end_date: date, currency: Currency = "CHF") -> StayQuote:
    """Every plan's price for one stay, in one request."""
    if end_date <= begin_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_date must be after begin_date",
        )

    # One snapshot for the whole response: every plan below is priced
    # against the same prices, promotions and exchange rates, so the figures
    # in one response can't have been computed from two different states.
    snapshot = await load_pricing_snapshot(currency)
    plans = await Plan.find_all().sort("price_ratio").to_list()
    stay = BookingDateRangeInput(begin_date=begin_date, end_date=end_date)

    plan_quotes: list[PlanQuote] = []
    for plan in plans:
        try:
            quote = quote_ranges_with(snapshot, [stay], plan_ratio(plan), currency)[0]
        except UnpricedDatesError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        plan_quotes.append(
            PlanQuote(
                plan_id=plan.id,
                plan_name=plan.name,
                price=quote.price,
                regular_price=quote.regular_price,
                discount=quote.discount,
                price_per_night=_per_night(quote.price, quote.nights),
                regular_price_per_night=_per_night(quote.regular_price, quote.nights),
                price_chf=quote.price_chf,
                regular_price_chf=quote.regular_price_chf,
                applied_promotions=[
                    QuotePromotion(
                        name=applied.name,
                        nights=applied.nights,
                        discount_total=applied.discount_total,
                        discount_type=applied.discount_type,
                        discount_ratio=applied.discount_ratio,
                    )
                    for applied in quote.applied_promotions
                ],
            )
        )

    return StayQuote(
        currency=currency,
        nights=(end_date - begin_date).days,
        min_stay_days=match_min_stay(snapshot.prices, begin_date),
        plans=plan_quotes,
    )


@public_router.get("/public/from", response_model=FromPriceQuote)
async def get_from_price(currency: Currency = "CHF") -> FromPriceQuote:
    """The "from ... / night" teaser: the cheapest nightly rate still ahead
    of us, at the cheapest plan's ratio, with the best offer on that rate's
    own date range."""
    snapshot = await load_pricing_snapshot(currency)
    today = date.today()

    # Rate windows that have fully elapsed can't be booked, so past pricing
    # must never surface as the lowest rate. Compared in CHF, since periods
    # may be quoted in different currencies.
    cheapest: tuple[Decimal, "date", "date"] | None = None
    for price in snapshot.prices:
        for rate_range in price.period.date_ranges:
            if rate_range.end_date < today:
                continue
            daily_rate_chf = convert_amount_with_rates(
                rate_range.daily_rate, price.period.currency, "CHF", snapshot.rates
            )
            if cheapest is None or daily_rate_chf < cheapest[0]:
                cheapest = (daily_rate_chf, rate_range.begin_date, rate_range.end_date)

    if cheapest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No nightly rate is configured"
        )

    daily_rate_chf, rate_begin_date, rate_end_date = cheapest
    plans = await Plan.find_all().to_list()
    ratio = min((plan_ratio(plan) for plan in plans), default=Decimal("1"))
    regular_chf = to_decimal(daily_rate_chf * ratio)

    best = best_promotion_overlapping(
        snapshot.promotions, rate_begin_date, rate_end_date, regular_chf, snapshot.rates
    )
    price_chf = to_decimal(regular_chf - best[1]) if best is not None else regular_chf

    return FromPriceQuote(
        currency=currency,
        price_per_night=convert_amount_with_rates(price_chf, "CHF", currency, snapshot.rates),
        regular_price_per_night=convert_amount_with_rates(regular_chf, "CHF", currency, snapshot.rates),
        price_per_night_chf=price_chf,
        regular_price_per_night_chf=regular_chf,
        promoted=best is not None,
        promotion_name=best[0].name if best is not None else None,
    )
