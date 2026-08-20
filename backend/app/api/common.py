"""Small helpers shared by the route modules.

These exist because the same few lines were being retyped in nearly every
router: fetch-or-404 appeared fourteen times across eight modules, and the
phone-normalization wrapper twice verbatim.
"""

from typing import TypeVar

from beanie import Document, PydanticObjectId
from fastapi import HTTPException, status

from app.core.identifiers import normalize_phone_number

D = TypeVar("D", bound=Document)


async def get_or_404(model: type[D], doc_id: PydanticObjectId, noun: str, **kwargs) -> D:
    """Fetch `doc_id` or raise 404 "<noun> not found".

    `kwargs` are passed through to Document.get (e.g. fetch_links=True).
    """
    document = await model.get(doc_id, **kwargs)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{noun} not found")
    return document


def normalize_phone_or_400(raw: str) -> str:
    """E.164-normalize a phone number, turning a parse failure into a 400."""
    try:
        return normalize_phone_number(raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
