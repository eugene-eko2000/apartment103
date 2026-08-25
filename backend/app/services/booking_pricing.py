"""Server-side authority for what a stay actually costs.

The price of a stay is derived here, from data only the server trusts: the
nightly rates stored on Price documents, the `price_ratio` of the chosen
Plan, and the Promotion documents that cover the nights being booked. A
booking request carries the *dates* and the *plan* the guest picked — never
an amount, and never a promotion id — so a tampered request can at worst
book a different (real, priced) plan, not invent its own price or its own
discount.

`quote_ranges` is the single quoting core: the quote endpoints
(app.api.routes.quotes) and booking creation
(app.api.routes.bookings._resolve_terms, through `price_date_ranges`) both
go through it, from the same dates and the same database, so a quote and the
booking made from it seconds later cannot disagree.

  base_chf     = rate(check-in date, in CHF) x plan.price_ratio
  for each night N in [begin_date, end_date):
      discount(N) = the largest discount, in CHF, among the promotions
                    eligible for N
      nightly(N)  = max(base_chf - discount(N), 0)
  price_chf    = sum of nightly(N)
  regular_chf  = base_chf x nights

Three details there are load-bearing rather than incidental:

* The *base* rate is still the one matched on the stay's check-in date, even
  when the stay spans a rate boundary. That is the rule the widget quotes
  from, and the quote is what the guest agreed to. Only the promotion lookup
  is per-night — which it has to be, since a promotion covers a date range
  that a stay may only partly overlap. A stay with no overlapping promotion
  therefore prices to exactly the figure it did before promotions existed.
* The CHF nightly figure is rounded to 2 places *before* being summed, the
  same convention this module has always used for the daily rate. Converting
  a stay total instead would drift by a rap of a cent against the quote.
* Promotions are compared per night in CHF, so a percentage and an absolute
  amount are commensurable and a stay can legitimately use promotion A for
  some of its nights and promotion B for others.

CHF is the pivot: rates and promotions live in whatever currency their own
document declares, the CHF subtotal is the canonical figure, and the
booking's own currency amount is converted from it.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.core.money import to_decimal
from app.models.booking import AppliedPromotion, BookingDateRange
from app.models.guest import Currency
from app.models.plan import Plan
from app.models.price import DateRangeRate, Price
from app.models.promotion import Promotion
from app.schemas.booking import BookingDateRangeInput
from app.services.currency_service import convert_amount_with_rates, rates_for

ZERO = Decimal("0.00")


class UnpricedDatesError(Exception):
    """Raised when a requested stay has no nightly rate to be priced from —
    its check-in date falls outside every configured Price range. Surfaces
    as a 400 rather than a 500: the dates are the client's input, and the
    widget's own calendar only offers dates that are covered."""

    def __init__(self, begin_date: date) -> None:
        super().__init__(f"No nightly rate is configured for {begin_date.isoformat()}")
        self.begin_date = begin_date


@dataclass
class NightBreakdown:
    """One night of a stay: what it would have cost, what it costs, and
    which promotion (if any) made the difference."""

    night: date
    regular_chf: Decimal
    price_chf: Decimal
    promotion: Promotion | None


@dataclass
class RangeQuote:
    """One priced date range, in both the requested currency and CHF."""

    begin_date: date
    end_date: date
    nights: int
    regular_price: Decimal  # in the requested currency
    price: Decimal
    discount: Decimal
    regular_price_chf: Decimal
    price_chf: Decimal
    applied_promotions: list[AppliedPromotion]


@dataclass
class PricingSnapshot:
    """Everything a quote reads from the database, fetched once.

    Held as a value so a caller pricing several plans over the same dates
    (the quote endpoint) does one read of prices, promotions and exchange
    rates for the whole response instead of one per plan — and, more
    importantly, so every plan in that response is priced against the very
    same data.
    """

    prices: list[Price]
    promotions: list[Promotion]
    rates: dict[Currency, Decimal]


def _match_rate(prices: list[Price], day: date) -> tuple[DateRangeRate, Currency] | None:
    """The nightly rate covering `day`, with the currency it is quoted in.

    First match wins, scanning periods in ascending begin_date order (and
    ranges within a period likewise — Period sorts them on validation), so
    an overlapping configuration resolves deterministically. `end_date` is
    inclusive here, matching DateRangeRate's own meaning of a rate window
    (unlike a stay's exclusive checkout date).
    """
    for price in prices:
        for rate_range in price.period.date_ranges:
            if rate_range.begin_date <= day <= rate_range.end_date:
                return rate_range, price.period.currency
    return None


def match_min_stay(prices: list[Price], day: date) -> int:
    """The hard minimum stay for a check-in on `day` — the one constraint
    that actually blocks a booking (a promotion's min_stay_days only gates
    its discount). 1 when no rate covers the date."""
    matched = _match_rate(prices, day)
    return matched[0].min_stay_days if matched is not None else 1


async def load_pricing_snapshot(currency: Currency) -> PricingSnapshot:
    """Read the prices, promotions and exchange rates needed to quote in
    `currency`.

    CHF is in the source currency set because the CHF subtotal itself gets
    converted into `currency`; a CHF quote off CHF rates and CHF promotions
    still needs no FX at all (see currency_service.rates_for).
    """
    prices = await Price.find_all().sort("period.begin_date").to_list()
    promotions = await Promotion.find(Promotion.active == True).to_list()  # noqa: E712
    rates = await rates_for(
        {price.period.currency for price in prices}
        | {promotion.currency for promotion in promotions}
        | {"CHF"},
        "CHF",
        currency,
    )
    return PricingSnapshot(prices=prices, promotions=promotions, rates=rates)


def _promotion_sort_key(promotion: Promotion) -> tuple[date, str]:
    """Tie-break order when two promotions offer the same discount on a
    night: earliest begin_date, then id. Deterministic and reproducible, so
    the quote endpoint and the booking made from it pick the same one."""
    return promotion.begin_date, str(promotion.id)


def _discount_chf(
    promotion: Promotion, base_chf: Decimal, rates: dict[Currency, Decimal]
) -> Decimal:
    """This promotion's discount on one night, in CHF, clamped to
    [0, base_chf] — `Money` is `ge=0`, and an absolute discount larger than
    the nightly price must leave the night free, never negative."""
    if promotion.discount_type == "percent":
        discount = to_decimal(base_chf * Decimal(str(promotion.discount_ratio)))
    else:
        discount = convert_amount_with_rates(promotion.discount_amount, promotion.currency, "CHF", rates)
    return min(max(discount, ZERO), base_chf)


def _best_promotion(
    promotions: list[Promotion],
    night: date,
    nights: int,
    base_chf: Decimal,
    rates: dict[Currency, Decimal],
) -> tuple[Promotion, Decimal] | None:
    """The promotion giving the largest CHF discount on `night`, or None.

    Eligibility is three separate conditions: the promotion is active, the
    night falls inside its (inclusive) range, and the stay being priced is
    long enough. `nights` is the night count of the whole booking date
    range, not of the overlapped subset — the requirement reads "if the
    booking fits minimum days requirements *and* overlaps with any promotion
    date range", so the two are independent tests.
    """
    best: tuple[Promotion, Decimal] | None = None
    for promotion in sorted(promotions, key=_promotion_sort_key):
        if not promotion.active:
            continue
        if not (promotion.begin_date <= night <= promotion.end_date):
            continue
        if nights < promotion.min_stay_days:
            continue
        discount = _discount_chf(promotion, base_chf, rates)
        if discount <= ZERO:
            continue
        # Strictly greater, over a list already in tie-break order, so the
        # earliest-begin_date-then-id promotion keeps the night on a tie.
        if best is None or discount > best[1]:
            best = (promotion, discount)
    return best


def _snapshot_promotions(
    nights_breakdown: list[NightBreakdown],
    currency: Currency,
    rates: dict[Currency, Decimal],
) -> list[AppliedPromotion]:
    """Group the per-night winners into one AppliedPromotion per distinct
    promotion, carrying its night count and summed discount.

    The snapshot is by value on purpose: once stored on a booking, editing
    or deleting the source Promotion must not change what that booking cost.
    """
    # Keyed by object identity rather than by document id: every night of
    # one quote resolves against the same snapshot list, so the same
    # promotion is literally the same object — and this stays correct for a
    # promotion that has no id yet.
    grouped: dict[int, tuple[Promotion, int, Decimal]] = {}
    for night in nights_breakdown:
        if night.promotion is None:
            continue
        key = id(night.promotion)
        promotion, count, total_chf = grouped.get(key, (night.promotion, 0, ZERO))
        grouped[key] = (promotion, count + 1, total_chf + (night.regular_chf - night.price_chf))

    return [
        AppliedPromotion(
            promotion_id=promotion.id,
            name=promotion.name,
            begin_date=promotion.begin_date,
            end_date=promotion.end_date,
            discount_type=promotion.discount_type,
            discount_ratio=promotion.discount_ratio,
            discount_amount=promotion.discount_amount,
            currency=promotion.currency,
            min_stay_days=promotion.min_stay_days,
            nights=count,
            discount_total=convert_amount_with_rates(to_decimal(total_chf), "CHF", currency, rates),
        )
        for promotion, count, total_chf in sorted(
            grouped.values(), key=lambda entry: _promotion_sort_key(entry[0])
        )
    ]


def quote_range(
    snapshot: PricingSnapshot,
    date_range: BookingDateRangeInput,
    ratio: Decimal,
    currency: Currency,
) -> RangeQuote:
    """Price one date range against an already-loaded snapshot."""
    matched = _match_rate(snapshot.prices, date_range.begin_date)
    if matched is None:
        raise UnpricedDatesError(date_range.begin_date)
    rate_range, rate_currency = matched

    daily_rate_chf = convert_amount_with_rates(rate_range.daily_rate, rate_currency, "CHF", snapshot.rates)
    base_chf = to_decimal(daily_rate_chf * ratio)
    nights = (date_range.end_date - date_range.begin_date).days

    breakdown: list[NightBreakdown] = []
    night = date_range.begin_date
    while night < date_range.end_date:
        best = _best_promotion(snapshot.promotions, night, nights, base_chf, snapshot.rates)
        discount_chf = best[1] if best is not None else ZERO
        breakdown.append(
            NightBreakdown(
                night=night,
                regular_chf=base_chf,
                price_chf=to_decimal(max(base_chf - discount_chf, ZERO)),
                promotion=best[0] if best is not None else None,
            )
        )
        night += timedelta(days=1)

    regular_price_chf = to_decimal(sum((n.regular_chf for n in breakdown), ZERO))
    price_chf = to_decimal(sum((n.price_chf for n in breakdown), ZERO))
    regular_price = convert_amount_with_rates(regular_price_chf, "CHF", currency, snapshot.rates)
    price = convert_amount_with_rates(price_chf, "CHF", currency, snapshot.rates)

    return RangeQuote(
        begin_date=date_range.begin_date,
        end_date=date_range.end_date,
        nights=nights,
        regular_price=regular_price,
        price=price,
        discount=to_decimal(regular_price - price),
        regular_price_chf=regular_price_chf,
        price_chf=price_chf,
        applied_promotions=_snapshot_promotions(breakdown, currency, snapshot.rates),
    )


def quote_ranges_with(
    snapshot: PricingSnapshot,
    ranges: list[BookingDateRangeInput],
    ratio: Decimal,
    currency: Currency,
) -> list[RangeQuote]:
    """Synchronous quoting against a caller-supplied snapshot, so one
    request can price several plans off a single database read."""
    return [quote_range(snapshot, date_range, ratio, currency) for date_range in ranges]


async def quote_ranges(
    ranges: list[BookingDateRangeInput], ratio: Decimal, currency: Currency
) -> list[RangeQuote]:
    """Price `ranges` at `ratio`, in `currency`. The shared quoting core."""
    if not ranges:
        return []
    return quote_ranges_with(await load_pricing_snapshot(currency), ranges, ratio, currency)


def plan_ratio(plan: Plan) -> Decimal:
    """A Plan's price ratio as a Decimal.

    Via str() rather than Decimal(float): price_ratio is stored as a float,
    and going through str keeps 0.85 as 0.85 instead of its binary expansion.
    """
    return Decimal(str(plan.price_ratio))


async def price_date_ranges(
    date_ranges: list[BookingDateRangeInput], plan: Plan, currency: Currency
) -> list[BookingDateRange]:
    """Price every requested stay from stored rates and promotions under
    `plan`.

    Returns ranges whose `price` is the final, discounted amount in
    `currency`, alongside the undiscounted `regular_price` and the by-value
    `applied_promotions` snapshot. Any `price` the caller's payload happened
    to carry is ignored outright — that is the whole point of this function.
    """
    return [
        BookingDateRange(
            begin_date=quote.begin_date,
            end_date=quote.end_date,
            price=quote.price,
            regular_price=quote.regular_price,
            applied_promotions=quote.applied_promotions,
        )
        for quote in await quote_ranges(date_ranges, plan_ratio(plan), currency)
    ]


def best_promotion_overlapping(
    promotions: list[Promotion],
    begin_date: date,
    end_date: date,
    base_chf: Decimal,
    rates: dict[Currency, Decimal],
) -> tuple[Promotion, Decimal] | None:
    """The largest CHF discount any active promotion offers on a nightly
    price of `base_chf` somewhere within the inclusive range
    [begin_date, end_date].

    Used only for the "from ... / night" teaser shown before any dates are
    picked (app.api.routes.quotes). `min_stay_days` is deliberately not
    tested here: there is no stay yet, so there is no night count to test it
    against — the teaser advertises the best offer that exists on the
    cheapest rate window, and the real, min-stay-aware figure arrives from
    the stay quote as soon as dates are chosen.
    """
    best: tuple[Promotion, Decimal] | None = None
    for promotion in sorted(promotions, key=_promotion_sort_key):
        if not promotion.active:
            continue
        if promotion.end_date < begin_date or promotion.begin_date > end_date:
            continue
        discount = _discount_chf(promotion, base_chf, rates)
        if discount <= ZERO:
            continue
        if best is None or discount > best[1]:
            best = (promotion, discount)
    return best
