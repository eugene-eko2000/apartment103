"""The public .ics feed Airbnb/Booking.com (or any calendar app) subscribes to.

Unauthenticated by necessity: an ICS consumer can't send an Authorization
header, so the unguessable token in the path is the credential — the same
design Airbnb's own export links use. Two kinds of token are accepted:
an ExternalCalendar's own export_token (that platform's feed, minus the
blocks it gave us), and the optional site-wide settings.calendar_export_token
(everything).
"""

import secrets

from fastapi import APIRouter, HTTPException, Response, status

from app.core.config import settings
from app.models.external_calendar import ExternalCalendar
from app.services.calendar_export import build_export_feed

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get(
    "/{token}.ics",
    response_class=Response,
    responses={200: {"content": {"text/calendar": {}}, "description": "iCalendar availability feed"}},
)
async def export_calendar_feed(token: str) -> Response:
    calendar = None
    site_token = settings.calendar_export_token
    # compare_digest, not ==: this is a secret compared against attacker-
    # supplied input on an anonymous endpoint.
    if not (site_token and secrets.compare_digest(token, site_token)):
        calendar = await ExternalCalendar.find_one(ExternalCalendar.export_token == token)
        if calendar is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar not found")

    body = await build_export_feed(calendar)
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={
            # A minute of caching is invisible next to the hours of
            # propagation delay the platforms add on their side, and keeps a
            # chatty consumer from rebuilding the feed on every poll.
            "Cache-Control": "public, max-age=60",
            "Content-Disposition": 'inline; filename="apartment103.ics"',
        },
    )
