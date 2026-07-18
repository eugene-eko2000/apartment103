import re
from typing import Literal

IdentifierKind = Literal["email", "phone"]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[0-9()\-\s]{6,20}$")


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
    return re.sub(r"[()\-\s]", "", identifier)


def normalize_phone_number(raw: str) -> str:
    """Validate and normalize a phone number, e.g. before storing it.

    Raises ValueError if `raw` isn't a syntactically valid phone number.
    """
    kind = classify_identifier(raw)
    if kind != "phone":
        raise ValueError("Invalid phone number")
    return normalize_identifier(raw, kind)
