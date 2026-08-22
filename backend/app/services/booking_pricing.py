"""Server-side authority for what a booking's date ranges actually cost.

The price of a stay is derived here, from data only the server trusts: the
nightly rates stored on Price documents and the `price_ratio` of the chosen
Plan. A booking request carries the *dates* and the *plan* the guest picked
— never an amount — so a tampered request can at worst book a different
(real, priced) plan, not invent its own price.

The arithmetic deliberately mirrors, step for step, what the booking widget
shows the guest before they commit (frontend/src/lib/pricing.ts
::findDailyRate plus the plan-ratio multiplication in BookingWidget.tsx):

  price_chf = nights x (daily rate of the *check-in* date, in CHF) x ratio

Two details there are load-bearing rather than incidental:

* The whole stay is charged at the rate matched on its check-in date, even
  when it spans a rate boundary. That is the rule the widget quotes from,
  and the quote is what the guest agreed to; pricing night-by-night here
  would silently charge a different figure than the one they saw.
* The CHF daily rate is rounded to 2 places *before* being multiplied out,
  again because that is the figure the widget multiplies. Converting the
  stay total instead would drift by a rap of a cent against the quote.

CHF is the pivot: rates live in whatever currency their Price period
declares, the CHF subtotal is the canonical figure, and the booking's own
currency amount is converted from it — the same CHF-baseline path that
produced the stored price before prices were computed here.
"""

from datetime import date
from decimal import Decimal

from app.core.money import to_decimal
from app.models.booking import BookingDateRange
from app.models.guest import Currency
from app.models.plan import Plan
from app.models.price import DateRangeRate, Price
from app.schemas.booking import BookingDateRangeInput
from app.services.currency_service import convert_amount_with_rates, rates_for


class UnpricedDatesError(Exception):
    """Raised when a requested stay has no nightly rate to be priced from —
    its check-in date falls outside every configured Price range. Surfaces
    as a 400 rather than a 500: the dates are the client's input, and the
    widget's own calendar only offers dates that are covered."""

    def __init__(self, begin_date: date) -> None:
        super().__init__(f"No nightly rate is configured for {begin_date.isoformat()}")
        self.begin_date = begin_date


def _match_rate(prices: list[Price], day: date) -> tuple[DateRangeRate, Currency] | None:
    """The nightly rate covering `day`, with the currency it is quoted in.

    First match wins, scanning periods in ascending begin_date order (and
    ranges within a period likewise — Period sorts them on validation), so
    an overlapping configuration resolves exactly the way findDailyRate
    resolves it for the same list on the client. `end_date` is inclusive
    here, matching DateRangeRate's own meaning of a rate window (unlike a
    stay's exclusive checkout date).
    """
    for price in prices:
        for rate_range in price.period.date_ranges:
            if rate_range.begin_date <= day <= rate_range.end_date:
                return rate_range, price.period.currency
    return None


async def price_date_ranges(
    date_ranges: list[BookingDateRangeInput], plan: Plan, currency: Currency
) -> list[BookingDateRange]:
    """Price every requested stay from stored rates under `plan`.

    Returns ranges whose `price` is denominated in `currency`. Any `price`
    the caller's payload happened to carry is ignored outright — that is the
    whole point of this function.
    """
    if not date_ranges:
        return []

    prices = await Price.find_all().sort("period.begin_date").to_list()
    # One rate lookup for the whole booking. CHF is in the source set
    # because the CHF subtotal itself gets converted into `currency` below;
    # a CHF booking priced off CHF rates still needs no FX at all (see
    # currency_service.rates_for).
    rates = await rates_for({price.period.currency for price in prices} | {"CHF"}, "CHF", currency)
    # Decimal(str(...)) rather than Decimal(float): price_ratio is stored as
    # a float, and going through str keeps 0.85 as 0.85 instead of its
    # binary expansion.
    ratio = Decimal(str(plan.price_ratio))

    priced: list[BookingDateRange] = []
    for date_range in date_ranges:
        matched = _match_rate(prices, date_range.begin_date)
        if matched is None:
            raise UnpricedDatesError(date_range.begin_date)
        rate_range, rate_currency = matched
        nights = (date_range.end_date - date_range.begin_date).days
        daily_rate_chf = convert_amount_with_rates(rate_range.daily_rate, rate_currency, "CHF", rates)
        price_chf = to_decimal(daily_rate_chf * nights * ratio)
        priced.append(
            BookingDateRange(
                begin_date=date_range.begin_date,
                end_date=date_range.end_date,
                price=convert_amount_with_rates(price_chf, "CHF", currency, rates),
            )
        )
    return priced
