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
without Stripe's own fee baked in — so this site's separate 2% commission
(COMMISSION_RATE below) is the only markup applied, instead of stacking on
top of Stripe's.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import stripe

from app.core.config import settings
from app.core.money import to_decimal
from app.models.guest import Currency

# The only currencies this app supports (mirrors app/models/guest.py::Currency
# and the 2-decimal-minor-unit assumption in stripe_service.py).
SUPPORTED_CURRENCIES: tuple[Currency, ...] = ("CHF", "EUR", "USD", "GBP")

# CHF is the currency all prices are stored in; FX quotes are requested for
# the other three, converting *into* CHF (see get_exchange_rates for why).
NON_CHF_CURRENCIES: tuple[Currency, ...] = tuple(c for c in SUPPORTED_CURRENCIES if c != "CHF")

COMMISSION_RATE = Decimal("0.02")

# The FX Quotes API is still in preview; Stripe requires this pinned on the
# request rather than picking up the account's default API version.
_FX_QUOTES_STRIPE_VERSION = "2025-06-30.preview"

_client = stripe.StripeClient(settings.stripe_secret_key)

_CACHE_TTL = timedelta(hours=1)
_cached_rates: dict[Currency, Decimal] | None = None
_cached_at: datetime | None = None


async def get_exchange_rates() -> dict[Currency, Decimal]:
    """Rates for 1 CHF in each supported currency (CHF: 1), sourced from a
    single Stripe FX quote and cached for _CACHE_TTL. No commission applied
    here — see convert_amount.

    A single quote with to_currency="chf" and from_currencies=[the other
    three] gives us rates in the "amount of CHF per 1 unit of X" direction;
    we invert each to get our own "amount of X per 1 CHF" convention.
    """
    global _cached_rates, _cached_at

    now = datetime.now(timezone.utc)
    if _cached_rates is not None and _cached_at is not None and now - _cached_at < _CACHE_TTL:
        return _cached_rates

    response = await asyncio.to_thread(
        _client.raw_request,
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

    _cached_rates = rates
    _cached_at = now
    return rates


async def convert_amount(amount: Decimal, from_currency: Currency, to_currency: Currency) -> Decimal:
    """Convert `amount` from one supported currency to another using live
    Stripe FX rates, adding a 2% commission whenever the target currency
    isn't CHF (converting into the base currency carries no markup)."""
    if from_currency == to_currency:
        return to_decimal(amount)

    rates = await get_exchange_rates()
    converted = (amount / rates[from_currency]) * rates[to_currency]
    if to_currency != "CHF":
        converted *= Decimal("1") + COMMISSION_RATE
    return to_decimal(converted)
