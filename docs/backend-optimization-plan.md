# Backend optimization plan

Review of `backend/` (FastAPI + Beanie/MongoDB + Stripe, ~5.3k LOC app code, ~3k LOC tests).

**Overall assessment:** the architecture is sound — clean layering (`api/routes` → `services` → `models`), a single money type, one place for FX, one place for charge scheduling, and genuinely good explanatory comments. The problems are not architectural; they are *volume* (six near-identical CRUD routers), *I/O discipline* (blocking network calls on the event loop, unprojected reads of a document that grows without bound), and a handful of caching/query details that will bite as data grows.

Nothing below is a request to change behaviour. Every item preserves the current API contract unless explicitly marked otherwise.

---

## Priority summary

| # | Item | Category | Impact | Effort | Est. LOC |
|---|------|----------|--------|--------|----------|
| B1 | Unbounded `Booking.webhook_events` + full-document saves | Suboptimal / scaling | **High** | M | −20 |
| B2 | Blocking SendGrid/Twilio/FPDF calls on the event loop | Suboptimal | **High** | S | ~0 |
| B3 | Unprojected list reads of heavy Booking documents | Suboptimal | **High** | S | ~0 |
| B4 | FX cache: no single-flight, no stale fallback | Suboptimal / robustness | **High** | S | +25 |
| B5 | Generic CRUD router factory (6 routers) | Duplication | Medium | M | **−230** |
| B6 | Case-insensitive regex lookup on `email` defeats the index | Suboptimal | Medium | S | −5 |
| B7 | Shared `get_or_404` / `_normalize_phone` helpers | Duplication | Medium | S | −40 |
| B8 | `_ensure_unique_contact`: 2 queries → 1 | Suboptimal | Low | S | −5 |
| B9 | Reconciliation job rewrites whole documents daily | Suboptimal | Medium | S | ~0 |
| B10 | Two competing Stripe client configurations | Overcomplexity | Low | S | −5 |
| B11 | `_build_display`: 2 coroutine awaits per money field | Suboptimal | Low | S | −10 |
| B12 | Overlap detection done in Python over all Active bookings | Suboptimal | Low | S | −5 |
| B13 | `_storage_dir()` mkdir on every image request | Suboptimal | Low | S | ~0 |
| B14 | Indexes live only in migrations, never on the models | Consistency risk | Low | M | +30 |
| B15 | Refund maths mirrored in frontend `refund.ts` | Cross-stack duplication | Low | M | see FE |

Net: roughly **−260 lines** of app code, with the highest-value work (B1–B4) being mostly *behavioural*, not line-count.

---

## 1. Suboptimal code

### B1 — `Booking.webhook_events` grows without bound, and every write rewrites the whole document

**Where:** [`app/models/booking.py:85-96,126`](../backend/app/models/booking.py), [`app/api/routes/payments.py:290-309`](../backend/app/api/routes/payments.py)

Every Stripe event that references a booking appends the **entire raw event payload** to `booking.webhook_events`, *and* the same payload is inserted into `PaymentEvent.data`. So each event is stored twice, and the booking document grows with each one.

Beanie's `Document.save()` is a full-document replace. That makes the write cost of a booking proportional to how many webhook events it has already accumulated — successive charges on a long booking rewrite an ever-larger document. It's O(n²) total bytes written over the life of a booking, and MongoDB's 16 MB document limit is a hard ceiling that a chatty PaymentIntent (with 3DS retries) can approach.

It also means `_apply_successful_charge` does *two* full saves (`booking.save()`, then another inside `_attach_fee_breakdown`) with the payload already appended.

**Proposal**

1. Make `PaymentEvent` the single owner of raw payloads. It already documents itself as "the canonical global audit trail", and it has a unique index on `stripe_event_id`.
2. Reduce `BookingWebhookEvent` to a reference: `stripe_event_id`, `event_type`, `received_at` — drop `data`. The admin panel can fetch the payload from `/payment-events/{id}` on expand (it is already lazy-expanded in the UI — see `WebhookEventItem` in `BookingsPanel.tsx`).
3. Replace the full `booking.save()` in the webhook path with a targeted atomic update:
   ```python
   await booking.update({
       "$push": {"webhook_events": event_ref.model_dump()},
       "$set": {"payment_status": ..., "amount_charged": ..., "charge_schedule": ...},
       "$inc": ...,
   })
   ```
   This also removes a lost-update window: today two concurrent webhooks for the same booking both read, mutate, and full-replace the document, so the second silently overwrites the first's changes.
4. Cap the list defensively: `$push` with `$slice: -50`.

**Payoff:** bounded document size, O(1) write cost per event, no double storage of payloads, and the concurrent-webhook race closed.

---

### B2 — Blocking network and CPU work runs on the async event loop

**Where:** [`app/core/notifications.py:32,51,83`](../backend/app/core/notifications.py), [`app/services/invoice.py:37`](../backend/app/services/invoice.py), [`app/api/routes/auth.py:100-103`](../backend/app/api/routes/auth.py), [`app/services/booking_emails.py:98-130`](../backend/app/services/booking_emails.py)

`send_text_email`, `send_html_email` and `send_sms` are **synchronous** functions that make blocking HTTPS calls (`SendGridAPIClient.send`, `TwilioClient.messages.create`). They are called from `async def` request handlers:

- `request_otp` (auth route) calls `send_otp_email` / `send_otp_sms` inline — every OTP request stalls the whole event loop for the duration of a SendGrid/Twilio round trip.
- `send_booking_confirmation_email` is `async def` but its body calls the blocking `send_html_email`, plus `build_charge_invoice_pdf` (FPDF rendering, CPU-bound) — all inside the Stripe webhook handler, on the loop.

`stripe_service.py` does this correctly (`asyncio.to_thread` everywhere) and even documents why. The notification path simply never got the same treatment. This is the single largest source of latency under concurrency: with one uvicorn worker, one OTP request blocks *all* other requests.

**Proposal**

- Wrap the three notification entry points in `asyncio.to_thread`, mirroring `stripe_service`:
  ```python
  async def send_html_email(...):
      ...
      await asyncio.to_thread(SendGridAPIClient(key).send, message)
  ```
  and make `send_otp_email` / `send_otp_sms` / `booking_emails.*` `async` all the way down.
- For OTP specifically, prefer FastAPI `BackgroundTasks`: the response does not depend on delivery, and the endpoint already returns a deliberately vague message. This drops p99 on `/auth/otp/request` from "SendGrid round trip" to "one Mongo insert".
- Move `build_charge_invoice_pdf` into `asyncio.to_thread` too — it is pure CPU inside a webhook handler that Stripe times out.

**Bonus:** `_send_email_safely(coro)` in `payments.py` already exists to swallow failures; once the callees are properly async, it does what its docstring claims.

---

### B3 — List endpoints load entire Booking documents to return three fields

**Where:** [`app/api/routes/bookings.py:31-37,156-177`](../backend/app/api/routes/bookings.py), [`app/services/availability.py:26`](../backend/app/services/availability.py), [`app/jobs/reconcile_payments.py:24`](../backend/app/jobs/reconcile_payments.py)

```python
bookings = await Booking.find(Booking.status == "Active").to_list()
return [BookedDateRange(...) for booking in bookings for date_range in booking.date_ranges]
```

This is the **public, unauthenticated** calendar endpoint. It reads every Active booking in full — including `charges`, `charge_schedule`, and (per B1) the accumulated raw Stripe payloads in `webhook_events` — over the wire from MongoDB, deserializes it all through Pydantic, and throws away everything but two dates. `find_overlapping_ranges` does the same, on the hot path of payment-intent creation.

Interacting with B1, this is the worst pairing in the codebase: an unbounded field being fully read by an anonymous endpoint on every calendar open.

**Proposal**

Use Beanie projections. Define small projection models and pass `projection_model=`:

```python
class BookingDatesProjection(BaseModel):
    date_ranges: list[BookedDateRange]

    class Settings:
        projection = {"date_ranges": 1}

bookings = await Booking.find(
    Booking.status == "Active", projection_model=BookingDatesProjection
).to_list()
```

Apply the same to:
- `list_public_booked_date_ranges` → `date_ranges` only
- `list_public_closed_date_ranges` → already light, but same pattern
- `find_overlapping_ranges` → `id`, `date_ranges`
- `list_bookings_display` → `currency`, `date_ranges`, `charges`, `charge_schedule` (no `webhook_events`)
- `reconcile_booking_payments` → it needs the full document to charge, but should exclude `webhook_events`

Also consider narrowing the admin `GET /bookings` response model: the frontend table renders name/dates/status, but the endpoint serializes every raw webhook payload for every booking on every panel load.

---

### B4 — The FX rate cache has no single-flight guard and no stale fallback

**Where:** [`app/services/currency_service.py:56-96`](../backend/app/services/currency_service.py)

```python
_cached_rates: dict[Currency, Decimal] | None = None
_cached_at: datetime | None = None

async def get_exchange_rates():
    if _cached_rates is not None and now - _cached_at < _CACHE_TTL:
        return _cached_rates
    response = await asyncio.to_thread(_client.raw_request, ...)
```

Three problems:

1. **Thundering herd.** The moment the 1-hour TTL expires, *every* in-flight request that touches a price sees a cold cache and fires its own `/v1/fx_quotes` call before any of them writes back. On a busy minute that is dozens of redundant Stripe calls. A single `asyncio.Lock` (double-checked inside) collapses them to one.
2. **No stale-while-error fallback.** If Stripe's FX Quotes API is down or rate-limits, `get_exchange_rates` raises and every public price/booking-display endpoint returns 500 — the whole site's pricing goes dark, even though a rates snapshot from 61 minutes ago would be perfectly serviceable. The endpoint is described as a *preview* API in the module docstring, which makes this more likely, not less.
3. **The cache is module-global mutable state**, which makes tests order-dependent and forces `test_currency_service.py` to reach in and reset it.

**Proposal**

```python
_lock = asyncio.Lock()
_HARD_STALE = timedelta(hours=24)

async def get_exchange_rates() -> dict[Currency, Decimal]:
    if _fresh():
        return _cached_rates
    async with _lock:
        if _fresh():                 # another waiter refreshed it
            return _cached_rates
        try:
            rates = await _fetch_rates()
        except Exception:
            logger.exception("FX quote fetch failed")
            if _cached_rates is not None and now - _cached_at < _HARD_STALE:
                return _cached_rates  # serve stale rather than 500
            raise
        ...
```

Optionally wrap the state in a small `RateCache` class so tests instantiate a fresh one instead of poking globals. Also: a background refresh task (the APScheduler instance already exists) would make the cache never-cold from a request's perspective.

---

### B6 — Case-insensitive regex email lookup cannot use the unique index

**Where:** [`app/api/routes/auth.py:39-42`](../backend/app/api/routes/auth.py)

```python
query = {"email": {"$regex": f"^{re.escape(identifier)}$", "$options": "i"}}
```

`$options: "i"` on a non-collated index forces a **collection scan** — the unique index created in `20260712000329_create_initial_collections.py` is not used. This runs on the login path, for both `admins` and `guests`.

It is also unnecessary: `normalize_identifier(..., "email")` lowercases the address, and both `guests.py` (`_normalize_email` on create/update) and `migrate.py create-admin` normalize on write. The stored value is already lowercase; `identifier` is already lowercase by the time `_find_principal` sees it.

**Proposal:** `query = {"email": identifier}`. If defence-in-depth against legacy mixed-case rows is wanted, do it properly with a case-insensitive collation on the index (`{locale: "en", strength: 2}`) rather than a regex — that stays index-backed. A one-off migration to lowercase existing `email` values makes the concern moot.

---

### B8 — `_ensure_unique_contact` issues two queries where one suffices

**Where:** [`app/api/routes/guests.py:29-37`](../backend/app/api/routes/guests.py)

Two sequential `find_one` round trips. One `$or` query returns both conflicts at once; the distinction between "email in use" and "phone in use" is recoverable from the returned document.

```python
conflict = await Guest.find_one({
    "$or": [{"email": email}, {"phone_number": phone_number}],
    "_id": {"$ne": exclude_id} if exclude_id else {"$exists": True},
})
```

Note this is also a check-then-write race: two simultaneous registrations with the same email both pass the check. The unique indexes exist, so the correct fix is to catch `pymongo.errors.DuplicateKeyError` on insert and translate it to 409 — the pre-check then becomes a nicety for good error messages rather than the enforcement mechanism.

---

### B9 — The reconciliation job full-writes every active booking daily

**Where:** [`app/jobs/reconcile_payments.py:27-44`](../backend/app/jobs/reconcile_payments.py)

```python
for booking in bookings:
    await charge_outstanding_balance(...)
    booking.last_payment_check_at = datetime.now(timezone.utc)
    await booking.save()
```

`booking.save()` runs unconditionally for every Active booking, replacing the whole document (webhook payloads and all — see B1) purely to stamp a timestamp. Worse, `charge_outstanding_balance` may have called `booking.save()` itself on the failure path, and this second save re-writes the in-memory object over it.

**Proposal**

```python
await booking.set({Booking.last_payment_check_at: datetime.now(timezone.utc)})
```
or a single `update_many` over all reconciled ids after the loop. Also consider pre-filtering the query — the job charges nothing for a booking with `payment_status == "fully_charged"`, so `Booking.find(status="Active", payment_status={"$ne": "fully_charged"})` skips most of the work. The `charge_outstanding_balance` comment says pre-filtering isn't needed for correctness, which is true, but it is worth it for cost once the booking history is non-trivial.

Sequential `await` in the loop is fine here (rate-limit friendliness with Stripe), but a bounded `asyncio.Semaphore(5)` + `gather` would cut wall-clock time if the booking count grows.

---

### B11 — `_build_display` awaits `convert_amount` once per money field

**Where:** [`app/api/routes/bookings.py:93-126`](../backend/app/api/routes/bookings.py)

A booking with 1 date range, 3 charges and 4 schedule entries triggers **18 awaits** of `convert_amount`, each of which awaits `get_exchange_rates()`. After B4's cache warms up, none of these hit the network, but every one is a coroutine allocation and a scheduler round trip; `list_bookings_display` multiplies it by the booking count in a sequential dict comprehension.

**Proposal:** fetch rates once at the top and use a synchronous converter:

```python
async def _build_display(booking, currency):
    rates = await get_exchange_rates()
    convert = partial(convert_with_rates, rates)   # pure, sync
    ...
```

Split `currency_service` into an async `get_exchange_rates()` and a pure `convert_amount_with_rates(amount, from, to, rates)`. Keep the existing `async def convert_amount` as a thin wrapper so no caller breaks. As a bonus, the pure function becomes trivially unit-testable without monkeypatching Stripe.

The same applies to `list_public_prices` in [`app/api/routes/prices.py:18-41`](../backend/app/api/routes/prices.py), which awaits twice per date range inside a nested comprehension.

---

### B12 — Overlap detection is a Python triple loop over all Active bookings

**Where:** [`app/services/availability.py:23-33`](../backend/app/services/availability.py)

Correct, and fine for a single apartment. Worth knowing that MongoDB can answer this directly, and the `bookings` index for "finding bookings that overlap a date range" already exists per the initial migration:

```python
await Booking.find({
    "status": "Active",
    "_id": {"$ne": booking.id},
    "date_ranges": {"$elemMatch": {"begin_date": {"$lt": own_end}, "end_date": {"$gt": own_begin}}},
}).to_list()
```

Combined with B3's projection, this turns an O(all bookings) scan into an index seek. Low urgency; note it as the intended shape when this stops being one property.

---

### B13 — `_storage_dir()` calls `mkdir` on every image request

**Where:** [`app/api/routes/images.py:55-58,89,131,172`](../backend/app/api/routes/images.py)

`_storage_dir()` runs `path.mkdir(parents=True, exist_ok=True)` — a blocking syscall — and is invoked from `get_image_file` (the dev-mode read path, potentially per image per page load), `upload_image`, and `delete_image`.

**Proposal:** create the directory once at startup in the `lifespan` handler and make `_storage_dir()` a plain `Path(settings.image_storage_path)`. In production nginx serves these files and this route is never hit, but in dev it is on every image.

---

## 2. Redundant / duplicated code

### B5 — Six CRUD routers are the same 60 lines with different nouns

**Where:** `admins.py` (59), `closures.py` (63), `cancellation_policies.py` (53), `plans.py` (72), `prices.py` (79), `categories.py` (53)

Every one of these implements the identical shape:

```python
@router.post("")     → Model(**payload.model_dump()); insert; return
@router.get("")      → Model.find_all().to_list()
@router.get("/{id}") → Model.get(id) or 404 "<Noun> not found"
@router.put("/{id}") → get or 404; assign each field; save
@router.delete("/{id}") → get or 404; delete
```

The `404` block alone — `if x is None: raise HTTPException(404, "<Noun> not found")` — appears **14 times** across the route modules. The PUT handlers manually re-assign each field one at a time (`admin.family_name = payload.family_name; admin.first_name = ...`), which is both verbose and a silent-drift hazard: add a field to a schema and you must remember to add a line to the PUT handler, or updates quietly ignore it.

**Proposal — a generic resource router factory**

```python
# app/api/crud.py
def make_crud_router[D: Document, C: BaseModel](
    *,
    model: type[D],
    create_schema: type[C],
    prefix: str,
    noun: str,
    dependencies: list[Depends] | None = None,
    sort: str | None = None,
    transform_create: Callable[[C], dict] | None = None,
    on_delete: Callable[[D], Awaitable[None]] | None = None,
) -> APIRouter:
    ...
```

- `admins` passes `transform_create` to normalize the phone number.
- `plans` passes `transform_create` to resolve `cancellation_policy_id` → a `Link`.
- `categories` passes `on_delete` for the "still has photos" guard, and keeps its bespoke POST (slug uniqueness + `sort_order` assignment) as an override.
- `prices`/`closures`/`cancellation_policies` need nothing extra.
- PUT becomes `for field, value in payload.model_dump().items(): setattr(doc, field, value)` — one implementation, no drift.

Keep the hand-written routers for `bookings`, `payments`, `images`, `guests` and `auth`, which have real domain logic. Expect the six generic modules to shrink from ~380 lines to ~150 (mostly the still-hand-written bits), and every future resource to cost 8 lines instead of 60.

**Caveat worth stating:** this trades explicitness for concision. If the team's preference is that route modules stay greppable and dumb, the smaller B7 below captures most of the value at none of the abstraction cost — take B7 and skip B5.

---

### B7 — Repeated helper functions across route modules

| Helper | Duplicated in |
|---|---|
| `_normalize_phone` (identical, 5 lines) | [`guests.py:18`](../backend/app/api/routes/guests.py), [`admins.py:12`](../backend/app/api/routes/admins.py) |
| `_get_cancellation_policy_or_404` (identical) | [`bookings.py:47`](../backend/app/api/routes/bookings.py), [`plans.py:17`](../backend/app/api/routes/plans.py) |
| `_get_X_or_404` pattern | 14 occurrences across 8 modules |
| `_get_booking_or_404` | `payments.py:31` — while `bookings.py` inlines the same check 4 times |

Note also that `payments.py` imports `_ensure_can_access_booking` — a **private** name — from `bookings.py`, and `bookings.py:246` calls it with keyword arguments in the opposite order to every other call site. That private-cross-module import is a coupling smell: the function is authorization logic, not routing logic.

**Proposal**

1. Add `app/api/common.py`:
   ```python
   async def get_or_404[D: Document](model: type[D], doc_id: PydanticObjectId, noun: str) -> D: ...
   def normalize_phone_or_400(raw: str) -> str: ...
   ```
2. Move `_ensure_can_access_booking`, `_booking_guest_id` and `_ensure_can_access_guest` into `app/api/deps.py` (or `app/services/authorization.py`) as public functions. `deps.py` already owns `Principal` and its `owns_guest` helper — this is exactly where they belong, and it removes the `payments → bookings` private import.
3. Normalize the `_ensure_can_access_booking(booking=..., principal=...)` call in `bookings.py:246` to positional, matching the other three sites.

---

### B10 — Two independent Stripe client configurations

**Where:** [`app/services/stripe_service.py:24`](../backend/app/services/stripe_service.py) sets the module-global `stripe.api_key = settings.stripe_secret_key`; [`app/services/currency_service.py:56`](../backend/app/services/currency_service.py) separately constructs `stripe.StripeClient(settings.stripe_secret_key)`.

`stripe_service.py`'s own docstring says "This module is the only place in the app that imports `stripe`" — which is no longer true (`currency_service.py`, `payments.py` and `payment_reconciliation.py` all import it). Both configuration styles also run at **import time**, so importing either module with an unset key produces a client in an odd half-configured state, which is why tests have to work around it.

**Proposal:** have `currency_service` call into `stripe_service` for its raw request (`stripe_service.raw_request(...)`), keeping one configured client, one place that knows the API key, and the docstring true again. Construct the client lazily on first use rather than at import.

---

### B15 — Refund percentage logic is implemented twice, across the stack

[`app/services/cancellation.py:23`](../backend/app/services/cancellation.py) `applicable_refund_percentage` and `frontend/src/lib/refund.ts` `applicableRefundPercentage` are line-for-line equivalent, and both files carry a comment saying "the two must stay in sync". The frontend copy exists for instant UI preview, which is a legitimate reason.

There is no free fix — the alternatives are (a) accept it and rely on the comments plus a shared test-vector fixture, or (b) have the booking/plan API return the already-computed refund bands so the client renders rather than calculates. Option (b) is the durable one: `CancellationTimeline` needs *bands with dates and amounts*, which is precisely what `charge_schedule.build_charge_schedule` already produces server-side. Exposing a `GET /plans/public?check_in=…` that includes the derived timeline would delete `refund.ts` entirely and remove a whole class of divergence bug.

Filed here rather than in the frontend plan because the backend is where the fix lives. Effort: M. Not urgent.

---

## 3. Overcomplexity

The backend is, on the whole, *not* over-engineered — most of what looks elaborate is genuinely load-bearing and well-justified in comments. Three smaller notes:

### B14 — Indexes are defined only inside migrations, never on the models

No Beanie `Settings.indexes` anywhere in `app/models/`. The indexes exist purely as side effects of migration files, which additionally **redefine every model from scratch** (`20260712000329_create_initial_collections.py` re-declares `CancellationPolicy`, `Guest`, `Booking`, `Admin`, `OtpChallenge`, `Price` — 275 lines of duplicated model definitions).

Duplicating models inside migrations is correct practice (a migration must be pinned to the schema as of its own point in time) and should stay. But *the current* index set living only in history means nothing validates that the running database matches expectations, and a developer reading `app/models/booking.py` cannot see what is indexed.

**Proposal:** declare the current indexes in each model's `Settings.indexes` as documentation-plus-verification. Beanie's `init_beanie` will create anything missing at startup, which converges the two sources rather than conflicting with them. Keep migrations authoritative for *changes*; make models authoritative for *current state*.

### `Money`'s JSON serializer converts Decimal to `float`

[`app/core/money.py:41-45`](../backend/app/core/money.py). The comment explains it is for wire compatibility with the float-expecting frontend, which is a real constraint. Worth revisiting eventually — every amount crossing the wire loses the exactness the entire `Decimal` apparatus exists to preserve, and `formatPrice` on the client just `Math.round`s it anyway. Serializing as a string and parsing to a number on the client would keep the invariant end-to-end. Low priority, medium blast radius.

### `_FULLY_CHARGED_EPSILON` and `_STATUS_SYNC_EPSILON` are the same constant, declared twice

[`payments.py:28`](../backend/app/api/routes/payments.py) and [`charge_schedule.py:23`](../backend/app/services/charge_schedule.py), both `Decimal("0.01")`, both with the same rationale in the comment. Move to `app/core/money.py` as `CHARGE_TOLERANCE` and import in both places — the tolerance is a money-domain fact, not a route-local one.

---

## 4. Suggested execution order

**Phase 1 — I/O correctness (highest value, lowest risk)**
1. B2 blocking notifications → `asyncio.to_thread` / `BackgroundTasks`
2. B3 projections on list reads
3. B4 FX cache: single-flight lock + stale fallback
4. B6 drop the regex email lookup

**Phase 2 — data model**
5. B1 webhook payload de-duplication + atomic `$push`/`$set` updates (needs a small migration and a frontend change to `BookingsPanel`)
6. B9 reconciliation job `set()` instead of `save()`
7. B8 duplicate-key handling on guest create

**Phase 3 — consolidation**
8. B7 shared `get_or_404` / phone normalization / authorization helpers ← *do this even if B5 is rejected*
9. B5 CRUD router factory
10. B10, B11, B12, B13, B14

**Phase 4 — optional / discuss first**
11. B15 server-computed cancellation bands (deletes frontend `refund.ts`)
12. `Money` wire format

Test coverage is good (~3k lines, including `test_charge_schedule.py`, `test_stripe_service.py`, `test_currency_service.py`), so Phases 1–3 should be safe to land incrementally with the existing suite as the guard.
