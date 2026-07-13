# Design: standards-based calendar sync (Airbnb / Booking.com compatible)

## Problem

apartment103 is a single listing that will very likely also be listed on Airbnb
and/or Booking.com. A guest can book through any of the three channels, so the
system needs to:

1. Stop the site from double-booking dates that are already taken on Airbnb or
   Booking.com.
2. Let Airbnb/Booking.com know which dates are taken on our own site, so they
   don't accept a booking we can't honor.

This only needs to solve *availability* sync (which dates are blocked), not
guest identity, messaging, or payments — those stay separate per channel.

## Why iCalendar (RFC 5545), not a "channel manager" integration

There are two tiers of calendar integration with OTAs:

- **Full channel-manager API integration** (Booking.com Connectivity API,
  Airbnb's partner API): real-time, two-way, carries price/guest/restriction
  data. Requires becoming an approved connectivity partner — not available to
  an individual host/small site, only to certified software vendors.
- **iCal (.ics) export/import**: the mechanism Airbnb, Booking.com, VRBO,
  Google Calendar, Apple Calendar and Outlook all support natively for
  *exactly this case* — a host with a listing on multiple sites pastes each
  platform's calendar URL into the others under "Sync calendars". It is
  pull-based, availability-only (no price, no guest info), and is the
  standard, zero-approval way to do this.

Given the scale (one apartment), **iCal sync is the right approach**: it is
literally the built-in feature Airbnb and Booking.com ship for hosts in our
position, it's a well-defined open standard (so it also works with Google/
Apple/Outlook calendars for free, as a bonus), and it needs no partner
approval. The doc below designs around it, and calls out the channel-manager
API path at the end as a future option if apartment103 ever manages multiple
units.

## Two sync directions

```
                 ┌────────────────────────┐
   poll (pull)   │                        │   export URL, pasted once
 ┌───────────────┤   apartment103 backend │◄──────────────────────────┐
 │               │                        │                            │
 │               └────────────┬───────────┘                            │
 │                             │ publishes                              │
 │                             ▼                                        │
 │                    GET /calendar/{token}.ics                         │
 │                             ▲                                        │
 ▼                             │                                        │
Airbnb export .ics    Booking.com import "Sync calendars"      Booking.com export .ics
Booking.com export .ics        pastes our URL                  Airbnb import "Sync calendars"
```

- **Inbound (Airbnb/Booking.com → us):** each platform gives a per-listing
  "export calendar" .ics URL. Our backend polls both on a schedule and turns
  their events into local `CalendarBlock` records, so our own booking flow
  sees those dates as unavailable.
- **Outbound (us → Airbnb/Booking.com):** we publish one .ics feed containing
  every confirmed booking (and any manual block) as an opaque "Reserved"
  event. The host pastes that URL into Airbnb's and Booking.com's "import a
  calendar" setting for the listing, once, during setup.

Both directions reuse the same standard: RFC 5545 `VEVENT`s with all-day
`DTSTART`/`DTEND`.

## Data model changes

Today `Booking` requires a linked `Guest` and a `cancellation_policy` — that's
right for bookings taken *on our site*, but external ICS feeds from Airbnb/
Booking.com are intentionally anonymized (no guest name, no price, per their
own privacy rules), so they don't fit that shape. Rather than making `Guest`
optional on `Booking` (which would weaken it everywhere else), add a separate,
narrow collection for opaque external unavailability:

```python
class BlockSource(str, Enum):
    AIRBNB = "airbnb"
    BOOKING_COM = "booking_com"
    MANUAL = "manual"          # host-entered block, e.g. maintenance

class CalendarBlock(Document):
    connection_id: PydanticObjectId | None   # which CalendarConnection produced this (None for manual)
    source: BlockSource
    external_uid: str | None                 # the VEVENT UID from the source feed, for diffing
    begin_date: date                         # inclusive
    end_date: date                           # exclusive (checkout day), matches Booking.date_ranges convention
    summary: str = "Reserved"                # whatever the remote feed sends, usually "Reserved"/"Airbnb (Not available)"
    last_seen_at: datetime                   # bumped on every sync pass; used to detect removed events

    class Settings:
        name = "calendar_blocks"
```

```python
class CalendarConnection(Document):
    source: BlockSource                      # AIRBNB | BOOKING_COM
    label: str                               # e.g. "Airbnb — apartment103"
    import_url: str                          # the .ics URL we pull from
    last_synced_at: datetime | None
    last_sync_status: Literal["ok", "error"] | None
    last_sync_error: str | None

    class Settings:
        name = "calendar_connections"
```

Availability for a candidate date range = no overlap with `Booking.date_ranges`
**and** no overlap with `CalendarBlock` ranges. Add a compound index on
`CalendarBlock` mirroring the existing `bookings` one:
`[("begin_date", 1), ("end_date", 1)]`, plus a unique index on
`(connection_id, external_uid)` so re-syncing the same feed upserts instead of
duplicating.

This is a new migration (`calendar_blocks` + `calendar_connections`
collections and their indexes), following the same
`free_fall_migration` pattern as `20260712000329_create_initial_collections.py`.

## Inbound sync (pulling Airbnb/Booking.com into our DB)

A scheduled job, one pass per `CalendarConnection`:

1. `GET` the connection's `import_url` (Python `icalendar` library to parse).
2. For each `VEVENT`, read `UID`, `DTSTART`, `DTEND` (all-day → `date`, not
   `datetime`).
3. Upsert a `CalendarBlock` keyed on `(connection_id, external_uid)`; stamp
   `last_seen_at = now`.
4. Delete any `CalendarBlock` for that connection whose `last_seen_at` wasn't
   just updated (its VEVENT disappeared from the feed → the OTA-side booking
   was cancelled).
5. Record `last_synced_at` / `last_sync_status` on the `CalendarConnection`
   either way, so sync failures are visible instead of silently stale.

**Scheduling:** run this every 30–60 minutes. Airbnb and Booking.com only
regenerate their own export feeds a few times a day themselves, so tighter
polling doesn't buy real-time accuracy — but it's cheap, so poll often enough
that the staleness window is small. Implementation can be an APScheduler job
inside the FastAPI process, or (simpler to reason about, matches the existing
Makefile-driven ops style) a small CLI command invoked by a system cron /
Docker cron sidecar, e.g. `uv run python -m app.calendar.sync`.

**Important caveat to design around:** iCal sync is not instant on either
side — Airbnb documents up to a few hours of propagation delay, Booking.com
similarly. This means there's always a small window where a booking made on
one channel hasn't yet appeared as a block on another. Two mitigations:
- Keep the poll interval short (30–60 min) to shrink the window.
- Give the host a manual "sync now" action (button in the admin calendar UI →
  triggers the same job on demand) for use right after they notice a new
  Airbnb/Booking.com reservation.
There's no way to fully eliminate this gap with iCal — it's inherent to the
pull-based standard, not a bug in this design. Full elimination would require
the partner-API tier mentioned above.

## Outbound feed (publishing our bookings to Airbnb/Booking.com)

`GET /calendar/{export_token}.ics` — generates the feed on demand (or cached
for a minute) from current `Booking` + manual `CalendarBlock` records:

```
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//apartment103//booking-calendar//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
UID:booking-<booking_id>@apartment103.example
DTSTAMP:20260713T000000Z
DTSTART;VALUE=DATE:20260801
DTEND;VALUE=DATE:20260805
SUMMARY:Reserved
STATUS:CONFIRMED
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
```

Key RFC 5545 details that matter for interop, since Airbnb/Booking.com parse
these feeds strictly:

- **All-day events**, not date-times: `DTSTART;VALUE=DATE` / `DTEND;VALUE=DATE`.
- **`DTEND` is exclusive** (the checkout date), same convention our own
  `BookingDateRange.end_date` already uses — so no translation needed, just
  serialize `begin_date`/`end_date` directly. Getting this wrong is the
  classic off-by-one that either double-blocks the checkout night or leaves a
  1-night gap unsynced.
- **Stable `UID` per booking**, unchanged across re-exports of the same
  booking (`booking-{id}@apartment103.example`), so the OTA's own diffing
  treats an edit as an update, not a cancel+recreate.
- **No PII in `SUMMARY`** — just "Reserved". No price is transmitted either
  (the format doesn't reliably carry it, and neither Airbnb nor Booking.com
  read price from an imported feed).
- **`{export_token}` is an unguessable random path segment** (not a real auth
  header — ICS consumers can't send one), the same pattern Airbnb's own
  export links use. Generate it once per connection/environment and treat it
  like a secret; rotating it invalidates whatever's pasted into Airbnb/
  Booking.com and requires re-pasting.

## Booking-creation flow changes

`create_booking`/`update_booking` in `app/api/routes/bookings.py` already need
an overlap check before this project (not yet implemented, per the current
code) — add it as part of this work, checking overlap against **both**
`Booking.date_ranges` and `CalendarBlock` ranges, so a booking can't be created
locally for a stretch that's actually taken on Airbnb/Booking.com but hasn't
been surfaced in the UI yet.

## Admin calendar UI (frontend)

A single visual calendar (e.g. [FullCalendar](https://fullcalendar.io/), which
consumes date ranges directly and needs no custom rendering) showing, color-
coded by source:

- Site bookings (`Booking`)
- Airbnb blocks (`CalendarBlock`, source=airbnb)
- Booking.com blocks (`CalendarBlock`, source=booking_com)
- Manual blocks (host-entered, e.g. for maintenance/personal use)

Plus:
- The export URL (`/calendar/{export_token}.ics`) displayed with a copy
  button, for pasting into Airbnb/Booking.com's "sync calendars" settings.
- A "sync now" button that triggers an on-demand inbound pull for both
  connections.
- Connection health (`last_synced_at` / `last_sync_status`) so a broken feed
  (Airbnb URL revoked, network error) is visible instead of silently causing
  drift.

## Testing/rollout plan

1. Stand up `CalendarConnection`/`CalendarBlock` + migration, unit-test the
   ICS parsing and the export generation against fixture `.ics` files
   (Airbnb's and Booking.com's real export formats differ slightly in field
   naming/comments — grab real sample exports during setup to fixture against,
   not hand-written ones).
2. Validate the outbound feed against Google Calendar first ("Add calendar →
   From URL") — it's a forgiving, widely-used ICS consumer, good for catching
   basic format errors before involving Airbnb/Booking.com.
3. Paste the outbound URL into a real Airbnb/Booking.com listing (or their
   sandbox/test listing if available) and confirm a test booking blocks the
   corresponding dates within their documented propagation window.
4. Paste their export URLs into our `CalendarConnection`s, make a test
   reservation on each platform, and confirm the inbound sync job creates a
   matching `CalendarBlock` and that our booking UI then refuses that date
   range.

## Future option: full channel-manager integration

If apartment103 grows to multiple units/listings, revisit the
Booking.com Connectivity API / Airbnb partner API path — real-time, two-way,
carries price and restrictions, no polling/propagation-delay caveat. It
requires a partner application and ongoing certification, which isn't
worthwhile for a single listing today; the `CalendarConnection`/
`CalendarBlock` split above is deliberately shaped so it could later be fed by
a real API webhook instead of ICS polling without changing the booking-side
overlap logic.
