"""Reading and writing iCalendar (RFC 5545) availability feeds.

The only thing that crosses this boundary is "these dates are taken": an
opaque UID and a half-open date range. No guest, no price — Airbnb and
Booking.com anonymize their own exports for privacy reasons and ignore
anything else in an imported feed.

Date convention: `end_date` is *exclusive* (the checkout day), matching both
RFC 5545's DTEND for all-day events and BookingDateRange/Closure elsewhere in
this codebase — so ranges serialize and parse with no translation. Getting
that wrong is the classic off-by-one that either blocks the checkout night on
the other platform or leaves a one-night gap unsynced.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from icalendar import Calendar, Event

logger = logging.getLogger(__name__)

PRODID = "-//apartment103//booking-calendar//EN"

# What we publish for every busy range. Deliberately constant and free of
# PII: the outbound feed's only job is to make the dates unbookable.
DEFAULT_SUMMARY = "Reserved"


@dataclass(frozen=True)
class IcsEvent:
    """One busy range, in either direction."""

    uid: str
    begin_date: date
    end_date: date  # exclusive
    summary: str = DEFAULT_SUMMARY


def build_calendar(events: Iterable[IcsEvent], *, now: datetime | None = None) -> bytes:
    """Serialize `events` as a VCALENDAR body.

    All-day VEVENTs (`DTSTART;VALUE=DATE`), which is what the OTAs emit and
    expect; a date-time DTSTART would make them interpret the block as a
    timed event and, depending on the platform, ignore it.
    """
    dtstamp = now or datetime.now(timezone.utc)

    calendar = Calendar()
    calendar.add("prodid", PRODID)
    calendar.add("version", "2.0")
    calendar.add("calscale", "GREGORIAN")
    # Ask consumers to re-poll every hour; most (Airbnb/Booking.com included)
    # use their own schedule regardless, but it costs one line to be polite.
    calendar.add("x-published-ttl", "PT1H")

    for event in events:
        component = Event()
        component.add("uid", event.uid)
        component.add("dtstamp", dtstamp)
        component.add("dtstart", event.begin_date)
        component.add("dtend", event.end_date)
        component.add("summary", event.summary)
        component.add("status", "CONFIRMED")
        component.add("transp", "OPAQUE")
        calendar.add_component(component)

    return calendar.to_ical()


def parse_calendar(raw: bytes | str) -> list[IcsEvent]:
    """Busy ranges found in an external feed.

    Tolerant on purpose: a single malformed VEVENT drops that event rather
    than failing the whole sync, since we don't control what the remote
    platform emits. Raises only if the payload isn't a parseable VCALENDAR
    at all — that's a broken URL (an HTML error page, say) and should be
    reported as a sync failure instead of silently importing nothing.
    """
    calendar = Calendar.from_ical(raw)

    events: list[IcsEvent] = []
    seen_uids: set[str] = set()
    for component in calendar.walk():
        event = _parse_event(component)
        if event is None:
            continue
        # A feed shouldn't repeat a UID, but if it does, the first occurrence
        # wins: (calendar, uid) is the upsert key on the way into Mongo.
        if event.uid in seen_uids:
            logger.warning("Ignoring duplicate VEVENT UID %s in feed", event.uid)
            continue
        seen_uids.add(event.uid)
        events.append(event)
    return events


def _parse_event(component) -> IcsEvent | None:
    status = str(component.get("status", "")).upper()
    if status == "CANCELLED":
        return None

    try:
        begin_date = _as_date(component.get("dtstart"))
        end_date = _event_end(component, begin_date)
    except (AttributeError, TypeError, ValueError):
        logger.warning("Skipping VEVENT with unreadable dates: %r", component.get("uid"), exc_info=True)
        return None

    if begin_date is None or end_date is None:
        return None
    # A zero- or negative-length event blocks nothing; treat it as the
    # single night it most likely meant.
    if end_date <= begin_date:
        end_date = begin_date + timedelta(days=1)

    uid = component.get("uid")
    summary = component.get("summary")
    return IcsEvent(
        # No UID is out of spec, but a feed missing one still has to sync
        # stably: key it on the dates, which is what identifies the block
        # anyway.
        uid=str(uid) if uid is not None else f"{begin_date.isoformat()}/{end_date.isoformat()}",
        begin_date=begin_date,
        end_date=end_date,
        summary=str(summary) if summary is not None else DEFAULT_SUMMARY,
    )


def _event_end(component, begin_date: date | None) -> date | None:
    """DTEND, or what RFC 5545 says to use when it's absent: DTSTART +
    DURATION, else the day after DTSTART for an all-day event."""
    dtend = component.get("dtend")
    if dtend is not None:
        return _as_date(dtend)
    if begin_date is None:
        return None
    duration = component.get("duration")
    if duration is not None:
        return begin_date + duration.dt
    return begin_date + timedelta(days=1)


def _as_date(property_value) -> date | None:
    """The calendar date of a DTSTART/DTEND, whether it came as VALUE=DATE
    (what the OTAs send) or as a date-time (what Google/Outlook send for a
    timed block)."""
    if property_value is None:
        return None
    value = property_value.dt
    if isinstance(value, datetime):
        # The wall-clock date at the event's own offset is the day the block
        # covers; converting to UTC first could shift it by one.
        return value.date()
    return value
