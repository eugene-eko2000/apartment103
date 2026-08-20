"""Currency conversion backed by Stripe's FX Quotes API.

Prices in this app are stored/quoted in CHF (see app/models/price.py,
app/models/booking.py). Guest-facing amounts in other currencies are
computed here and only here — no raw exchange rate ever leaves the backend;
callers only ever see the domain API responses that embed already-converted
amounts (see app/api/routes/prices.py, app/api/routes/bookings.py).

Stripe's older `stripe.ExchangeRate` resource (tried first) is deprecated
and now returns 404 "Unrecognized request URL" — verified against this
project's own Stripe test account. Its replacement, the FX Quotes API
(POST /v1/fx_quotes), is itself still in preview and requires an explicit
`.preview`-suffixed Stripe-Version request header, so we call it as a raw
request rather than through a typed SDK resource (the installed
stripe-python has no `FxQuote` class yet).

A quote is normally a *locked* rate meant to be reused for an actual
Stripe-executed conversion (`lock_duration`/`lock_expires_at`/`lock_status`
in the response). We don't execute conversions through Stripe — guests are
always charged directly in their chosen currency — so we only read the rate
out of the quote and let it expire; `lock_duration="hour"` just keeps our
own request cadence aligned with the in-process cache below.

Each currency in the response carries several rate variants
(rates.<ccy>.rate_details): `reference_rate` is the raw third-party
(ECB) market rate, `base_rate` is Stripe's own rate before Stripe's fee, and
`exchange_rate` is base_rate with Stripe's *own* ~2% fx_fee_rate + a small
duration premium already deducted. We use `base_rate` — Stripe's rate,
without Stripe's own fee baked in — so this site's separate commission
(settings.commission_rate) is the only markup applied, instead of stacking
on top of Stripe's.
"""

import asyncio
import logging
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.core.config import settings
from app.core.money import to_decimal
from app.models.guest import Currency
from app.services import stripe_service

logger = logging.getLogger(__name__)

# The only currencies this app supports (mirrors app/models/guest.py::Currency
# and the 2-decimal-minor-unit assumption in stripe_service.py).
SUPPORTED_CURRENCIES: tuple[Currency, ...] = ("CHF", "EUR", "USD", "GBP")

# CHF is the currency all prices are stored in; FX quotes are requested for
# the other three, converting *into* CHF (see get_exchange_rates for why).
NON_CHF_CURRENCIES: tuple[Currency, ...] = tuple(c for c in SUPPORTED_CURRENCIES if c != "CHF")

# The FX Quotes API is still in preview; Stripe requires this pinned on the
# request rather than picking up the account's default API version.
_FX_QUOTES_STRIPE_VERSION = "2025-06-30.preview"

_CACHE_TTL = timedelta(hours=1)

# How long a cached snapshot may keep being served *after a refresh has
# failed*. Rates move slowly enough that a day-old quote is far better than
# every priced endpoint returning 500 because Stripe's FX Quotes API — still
# a preview API, see the module docstring — is unavailable.
_HARD_STALE_AFTER = timedelta(hours=24)

_cached_rates: dict[Currency, Decimal] | None = None
_cached_at: datetime | None = None

# Collapses concurrent refreshes into a single Stripe call. Without it,
# every request in flight at the moment the TTL expires sees a cold cache
# and fires its own /v1/fx_quotes before any of them writes back.
_refresh_lock = asyncio.Lock()


def _cache_age(now: datetime) -> timedelta | None:
    """Age of the cached snapshot, or None if nothing is cached yet."""
    if _cached_rates is None or _cached_at is None:
        return None
    return now - _cached_at


async def _fetch_rates() -> dict[Currency, Decimal]:
    """One Stripe FX quote -> our "amount of X per 1 CHF" convention.

    A single quote with to_currency="chf" and from_currencies=[the other
    three] gives us rates in the "amount of CHF per 1 unit of X" direction;
    we invert each.
    """
    response = await stripe_service.raw_request(
        "post",
        "/v1/fx_quotes",
        from_currencies=[c.lower() for c in NON_CHF_CURRENCIES],
        to_currency="chf",
        lock_duration="hour",
        stripe_version=_FX_QUOTES_STRIPE_VERSION,
    )
    quote_rates = response.data["rates"]

    rates: dict[Currency, Decimal] = {"CHF": Decimal("1")}
    for currency in NON_CHF_CURRENCIES:
        chf_per_unit = Decimal(str(quote_rates[currency.lower()]["rate_details"]["base_rate"]))
        rates[currency] = Decimal("1") / chf_per_unit
    return rates


async def get_exchange_rates() -> dict[Currency, Decimal]:
    """Rates for 1 CHF in each supported currency (CHF: 1), sourced from a
    single Stripe FX quote and cached for _CACHE_TTL. No commission applied
    here — see convert_amount.

    Refreshes are single-flighted through _refresh_lock, and a failed
    refresh falls back to the last good snapshot for up to
    _HARD_STALE_AFTER rather than failing the request.
    """
    global _cached_rates, _cached_at

    now = datetime.now(timezone.utc)
    age = _cache_age(now)
    if age is not None and age < _CACHE_TTL:
        return _cached_rates  # type: ignore[return-value]

    async with _refresh_lock:
        # Re-check under the lock: another coroutine may have refreshed
        # while this one was queued, in which case there is nothing to do.
        now = datetime.now(timezone.utc)
        age = _cache_age(now)
        if age is not None and age < _CACHE_TTL:
            return _cached_rates  # type: ignore[return-value]

        stale_rates = _cached_rates
        try:
            rates = await _fetch_rates()
        except Exception:
            logger.exception("Stripe FX quote fetch failed")
            if stale_rates is not None and age is not None and age < _HARD_STALE_AFTER:
                logger.warning("Serving exchange rates cached %s ago", age)
                return stale_rates
            raise

        _cached_rates = rates
        _cached_at = now
        return rates


async def rates_for(source_currencies: "Iterable[Currency]", *targets: Currency) -> dict[Currency, Decimal]:
    """Rates needed to convert from `source_currencies` into `targets` — or
    an empty table when every conversion is a no-op.

    convert_amount_with_rates short-circuits on same-currency before it
    looks at the table, so callers whose data is already in the requested
    currency (a CHF price list rendered in CHF, the common case) never touch
    Stripe at all. Without this, hoisting the rate fetch out of the loop
    would have turned those into a network round trip.
    """
    if any(source != target for source in source_currencies for target in targets):
        return await get_exchange_rates()
    return {}


def convert_amount_with_rates(
    amount: Decimal, from_currency: Currency, to_currency: Currency, rates: dict[Currency, Decimal]
) -> Decimal:
    """The conversion itself, against an already-fetched rate table.

    Pure and synchronous, so a caller converting many amounts (a booking's
    date ranges, charges and schedule entries; a price list's date ranges)
    fetches rates once and then just does arithmetic, instead of awaiting a
    coroutine per field.
    """
    if from_currency == to_currency:
        return to_decimal(amount)

    # Commission is charged on the CHF amount, before the destination rate
    # is applied -- the markup is a CHF-denominated fee, so it is defined
    # against the base currency rather than against whatever the guest's
    # currency happens to be. Converting *into* CHF carries no markup.
    in_chf = amount / rates[from_currency]
    if to_currency != "CHF":
        in_chf *= Decimal("1") + settings.commission_rate
    return to_decimal(in_chf * rates[to_currency])


async def convert_amount(amount: Decimal, from_currency: Currency, to_currency: Currency) -> Decimal:
    """Convert `amount` from one supported currency to another using live
    Stripe FX rates, applying settings.commission_rate to the CHF amount
    before the destination rate whenever the target currency isn't CHF
    (converting into the base currency carries no markup).

    Thin wrapper over convert_amount_with_rates for one-off conversions.
    """
    if from_currency == to_currency:
        return to_decimal(amount)
    return convert_amount_with_rates(amount, from_currency, to_currency, await get_exchange_rates())
