"""Small helpers shared by the route modules.

These exist because the same few lines were being retyped in nearly every
router: fetch-or-404 appeared fourteen times across eight modules, and the
phone-normalization wrapper twice verbatim.
"""

from typing import TypeVar

from beanie import Document, PydanticObjectId
from fastapi import HTTPException, status

from app.core.identifiers import normalize_phone_number
from app.models.guest import Guest

D = TypeVar("D", bound=Document)

# Refused rather than silently allowed: writing to a redacted guest would put
# a real person's details back onto the document their data was retired from,
# re-attaching them to every booking it still links to.
_GUEST_RETIRED = (
    "This guest's personal data has been retired under the data retention policy. "
    "They must register again as a new guest."
)


async def get_or_404(model: type[D], doc_id: PydanticObjectId, noun: str, **kwargs) -> D:
    """Fetch `doc_id` or raise 404 "<noun> not found".

    `kwargs` are passed through to Document.get (e.g. fetch_links=True).
    """
    document = await model.get(doc_id, **kwargs)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{noun} not found")
    return document


def ensure_guest_not_redacted(guest: Guest) -> None:
    """Refuse to reuse a guest whose data the retention sweep has wiped.

    Only admins can reach the paths that call this — a redacted guest's own
    token stops authenticating the moment they are wiped (see
    app.api.deps.get_current_principal) — so the point here is that not even
    an admin can bring the old record back into service. A returning guest
    goes through registration again and gets a new document; see
    app.services.data_retention for why the old one has to stay behind.
    """
    if guest.is_redacted:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_GUEST_RETIRED)


def normalize_phone_or_400(raw: str) -> str:
    """E.164-normalize a phone number, turning a parse failure into a 400."""
    try:
        return normalize_phone_number(raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
