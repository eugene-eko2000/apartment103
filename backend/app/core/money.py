"""Shared money/Decimal helpers.

All price/amount fields in this app are stored and computed as
decimal.Decimal, quantized to 2 places, rather than float — repeated
charge/refund arithmetic on floats accumulates binary rounding drift that
Decimal avoids. MongoDB has no native Decimal type, so Beanie round-trips
these through bson.Decimal128; to_decimal() unwraps that (plus floats,
ints, and strings) into a plain, 2-place Decimal.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

import bson
from pydantic import BeforeValidator, PlainSerializer

TWO_PLACES = Decimal("0.01")


def to_decimal(value) -> Decimal | None:
    """Coerce int/float/str/Decimal/bson.Decimal128 to a Decimal quantized
    to 2 places. Floats are converted via str() to avoid binary artifacts."""
    if value is None:
        return None
    if isinstance(value, bson.Decimal128):
        value = value.to_decimal()
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def format_money(amount: Decimal, currency: str) -> str:
    return f"{to_decimal(amount):,.2f} {currency}"


# Field type for prices/amounts: stored and computed as Decimal (so
# repeated charge/refund arithmetic doesn't accumulate float drift), but
# serialized back to a plain JSON number rather than a decimal string, so
# API responses stay wire-compatible with existing (float-expecting)
# frontend consumers.
Money = Annotated[
    Decimal,
    BeforeValidator(to_decimal),
    PlainSerializer(lambda v: float(v) if v is not None else None, return_type=float, when_used="json"),
]
