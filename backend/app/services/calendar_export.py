"""Outbound half of calendar sync: our booked dates as an .ics feed.

This is the "our calendar -> external calendar" direction. iCal is
pull-based, so we don't push anything: we publish a feed at
GET /calendar/{token}.ics and the host pastes that URL into each platform's
"sync calendars" setting once, after which the platform polls it and blocks
the dates it finds.

Each ExternalCalendar gets its own token, and the feed served for it leaves
out the closures that came *from* that same calendar. That serves two ends:
Airbnb never sees its own reservations echoed back (which, with each side's
propagation delay, can leave a cancelled block bouncing between the two),
and everything else — site bookings, manual closures, and the blocks
imported from the *other* platforms — still reaches it, so a Booking.com
reservation blocks the dates on Airbnb without the host having to cross-paste
every platform's URL into every other platform.
"""

import logging

from beanie import PydanticObjectId

from app.core.config import settings
from app.models.booking import Booking
from app.models.closure import Closure
from app.models.external_calendar import ExternalCalendar
from app.schemas.booking import BookingExportProjection
from app.services.ics import IcsEvent, build_calendar

logger = logging.getLogger(__name__)


def _uid(kind: str, document_id: PydanticObjectId, suffix: str = "") -> str:
    """Stable per-event UID.

    Stable is the point: an OTA diffs an imported feed by UID, so reusing the
    same one across exports makes an edited booking an update rather than a
    cancellation followed by a new reservation.
    """
    return f"{kind}-{document_id}{suffix}@{settings.calendar_uid_domain}"


async def collect_export_events(exclude_calendar_id: PydanticObjectId | None = None) -> list[IcsEvent]:
    """Every date range we want other platforms to treat as unavailable.

    :param exclude_calendar_id: skip closures imported from this calendar —
        set when building the feed that calendar itself will read.
    """
    # Only Active bookings: a Pending one is mid-checkout and may never be
    # paid for, and it doesn't block our own public calendar either (see
    # app.api.routes.bookings.list_public_booked_date_ranges).
    bookings = await Booking.find(
        Booking.status == "Active", projection_model=BookingExportProjection
    ).to_list()
    events = [
        # Suffixed by position because one booking can hold several date
        # ranges (e.g. split across two price periods), and every VEVENT in
        # a feed needs its own UID.
        IcsEvent(
            uid=_uid("booking", booking.id, f"-{index}"),
            begin_date=date_range.begin_date,
            end_date=date_range.end_date,
        )
        for booking in bookings
        for index, date_range in enumerate(booking.date_ranges)
    ]

    closure_filter: dict = {}
    if exclude_calendar_id is not None:
        closure_filter = {"external_calendar_id": {"$ne": exclude_calendar_id}}
    closures = await Closure.find(closure_filter).to_list()
    events.extend(
        IcsEvent(uid=_uid("closure", closure.id), begin_date=closure.begin_date, end_date=closure.end_date)
        for closure in closures
    )
    return events


async def build_export_feed(calendar: ExternalCalendar | None = None) -> bytes:
    """The .ics body served at /calendar/{token}.ics.

    `calendar` is the ExternalCalendar the token belongs to, or None for the
    site-wide feed (settings.calendar_export_token), which carries
    everything and is what to point Google Calendar at when verifying the
    format.
    """
    events = await collect_export_events(exclude_calendar_id=calendar.id if calendar else None)
    return build_calendar(events)
