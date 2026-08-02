import re
from typing import Literal

import phonenumbers

IdentifierKind = Literal["email", "phone"]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[0-9()\-\s]{6,20}$")

# Region assumed for phone numbers typed without an explicit country code
# (e.g. a guest logging in with "078 123 45 67" instead of "+41781234567").
# Matches PhoneInput's defaultCountry on the frontend.
_DEFAULT_PHONE_REGION = "CH"


def classify_identifier(identifier: str) -> IdentifierKind:
    identifier = identifier.strip()
    if "@" in identifier:
        if not _EMAIL_RE.match(identifier):
            raise ValueError("Invalid email address")
        return "email"
    if not _PHONE_RE.match(identifier):
        raise ValueError("Invalid phone number")
    return "phone"


def normalize_identifier(identifier: str, kind: IdentifierKind) -> str:
    identifier = identifier.strip()
    if kind == "email":
        return identifier.lower()
    return normalize_phone_number(identifier)


def normalize_phone_number(raw: str) -> str:
    """Validate and canonicalize a phone number to E.164.

    Different ways of typing the same real-world number (missing country
    code, spacing, punctuation, ...) must normalize to the same string, or a
    returning guest who types their number slightly differently than before
    won't be matched to their existing account at login. Raises ValueError
    if `raw` isn't a syntactically valid phone number.
    """
    if classify_identifier(raw) != "phone":
        raise ValueError("Invalid phone number")
    try:
        parsed = phonenumbers.parse(raw.strip(), _DEFAULT_PHONE_REGION)
    except phonenumbers.NumberParseException as exc:
        raise ValueError("Invalid phone number") from exc
    if not phonenumbers.is_possible_number(parsed):
        raise ValueError("Invalid phone number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
