# Design: Stripe payment integration (custom UI, backend-orchestrated)

## Problem

Today booking creation (`POST /bookings` in `app/api/routes/bookings.py`)
collects no money at all — the widget explicitly tells guests "No charge yet."
Cancellation (`POST /bookings/{id}/cancel`) just flips `status` to
`Cancelled`; the refund percentage shown to the guest
(`frontend/src/lib/refund.ts`) is a client-side display calculation with no
backend enforcement and no actual charge or refund behind it.

We need real payment collection that matches the site's existing
free-cancellation-window cancellation policies:

1. On booking, if the guest is inside the free-cancellation zone, only verify
   the card (no charge).
2. As check-in approaches and the cancellation policy's refund percentage
   drops, charge the newly non-refundable portion.
3. Once the policy is fully non-refundable, the full amount should have been
   captured.
4. All charges happen in the guest's currency for that booking.

This must be built with **custom UI, full control over the flow**, using
Stripe only as a backend-orchestrated payment processor — not Stripe
Checkout's hosted page.

## Core principle: backend-only orchestration, frontend collects cards only

All money decisions — creating intents, computing amounts, deciding when to
charge — happen exclusively in the backend. The frontend's only Stripe
touchpoint is Stripe.js/Elements, used to collect card details and send them
directly to Stripe, never through our servers.

This isn't a workaround, it's required: letting raw card numbers touch our
backend would put us in PCI SAQ D scope. Elements' `appearance` API allows
full visual styling to match the existing UI (it only iframes the sensitive
input fields), so "custom UI" and "backend-only orchestration" aren't in
tension — we just never see the PAN.

## The accrual model

Rather than three separate behaviors ("verify", "charge fee", "charge rest"),
model this as one invariant, checked daily:

```
amount_charged  ==  total_price × (1 − current_refund_percentage)
```

`current_refund_percentage` is what the guest would get back if they
cancelled *right now*, per the same rule-matching logic as
`applicableRefundPercentage` in `frontend/src/lib/refund.ts` (highest
`days_before_checkin` threshold ≤ actual days-before-check-in wins, 0% if
none match). The right-hand side is the amount the guest would forfeit on
cancellation today — i.e. the money that's already "earned" and safe to
capture.

A daily job recomputes the right-hand side and charges the difference. As the
refund percentage steps down toward 0% approaching check-in, the target rises
toward `total_price` — so "charge the rest of the full sum" isn't a special
case, it's just the last daily increment converging to 100%. And because
charged money is always exactly the forfeitable amount as of that moment,
cancellation essentially never needs a Stripe refund — see below.

## Stripe objects used

- **Customer** — one per `Guest`, created lazily on first booking.
- **SetupIntent** (`usage=off_session`) — booking made in the fully-refundable
  zone: verify/save a card, nothing charged.
- **PaymentIntent** — booking made where a fee already applies at booking
  time, and every subsequent daily accrual charge. Uses `off_session=True,
  confirm=True` with the stored `payment_method` for the daily job (guest not
  present); uses on-session confirmation via Elements when the guest is
  actively completing the booking flow.
- **Webhooks are the source of truth.** The DB is only ever updated from a
  verified webhook event, never from the client's "it succeeded" callback.

## Booking-time behavior

The user's spec covers the free-cancellation case; the same principle needs
to cover a booking made *close to check-in*, where a fee already applies on
day one:

1. Compute `refund_percentage` at booking time.
2. **`refund_percentage == 1.0`** (free-cancellation zone) → create a
   `SetupIntent`. Card verified, $0 charged.
3. **`0 < refund_percentage < 1`** → create a `PaymentIntent` for
   `total_price × (1 − refund_percentage)`, with `setup_future_usage=
   off_session` so the card is also saved for future daily charges. Guest
   confirms on-session (3DS if required).
4. **`refund_percentage == 0`** (booked inside the fully non-refundable
   window) → `PaymentIntent` for the full `total_price`, confirmed
   on-session. Nothing left for the daily job to do.

## Database changes (Beanie / MongoDB)

**`Guest`** (`app/models/guest.py`) — add:

```python
stripe_customer_id: str | None = None
```

**`Booking`** (`app/models/booking.py`) — add:

```python
class BookingCharge(BaseModel):
    stripe_payment_intent_id: str
    amount: float
    currency: Currency
    reason: Literal["initial_charge", "scheduled_accrual", "cancellation_settlement"]
    status: Literal["succeeded", "requires_action", "failed"]
    created_at: datetime

class BookingRefund(BaseModel):
    stripe_refund_id: str
    amount: float
    currency: Currency
    reason: str
    created_at: datetime

PaymentStatus = Literal[
    "card_verification_pending", "card_verified",   # SetupIntent path
    "partially_charged", "fully_charged",            # accrual in progress / done
    "requires_action", "failed",                     # needs guest or admin attention
]

class Booking(Document):
    ...
    stripe_payment_method_id: str | None = None   # card saved for this booking's off-session charges
    payment_status: PaymentStatus = "card_verification_pending"
    amount_charged: float = 0.0
    charges: list[BookingCharge] = Field(default_factory=list)
    refunds: list[BookingRefund] = Field(default_factory=list)
    last_payment_check_at: datetime | None = None
    last_payment_error: str | None = None
```

`amount_charged` plus the `charges`/`refunds` audit trail avoids re-deriving
anything from Stripe on every read, and gives the admin panel and support
disputes a full record without a live API call.

**New collection `PaymentEvent`** (`app/models/payment_event.py`) — dedupe
ledger for incoming webhooks, since Stripe retries delivery:

```python
class PaymentEvent(Document):
    stripe_event_id: str = Field(unique=True)
    event_type: str
    processed_at: datetime
    booking_id: PydanticObjectId | None = None

    class Settings:
        name = "payment_events"
```

This is a new migration (new fields + `payment_events` collection with a
unique index on `stripe_event_id`), following the same pattern as the
existing `backend/migrations/*.py` files.

## New backend module: `app/services/cancellation.py`

Port `applicableRefundPercentage` from `frontend/src/lib/refund.ts` verbatim
into Python. This becomes the **only** authoritative implementation for
anything that moves money; the TypeScript copy stays for instant UI preview
only, never for actual charging decisions. Reference check-in date =
`min(dr.begin_date for dr in booking.date_ranges)`.

## New backend routes: `app/api/routes/payments.py`

- `POST /bookings/{id}/payment/intent` — called right after
  `POST /bookings` succeeds. Computes the current refund %, creates/reuses
  the Stripe Customer, and returns `{mode: "setup" | "payment", client_secret,
  amount, currency}` per the booking-time logic above.
- `POST /webhooks/stripe` — signature-verified (`STRIPE_WEBHOOK_SECRET`),
  idempotent via `PaymentEvent`. Handles:
  - `setup_intent.succeeded` → store `stripe_payment_method_id`,
    `payment_status = "card_verified"`
  - `payment_intent.succeeded` → append `BookingCharge`, bump
    `amount_charged`, update `payment_status`
  - `payment_intent.payment_failed` → set `last_payment_error`,
    `payment_status = "failed"`
  - `charge.refunded` → append `BookingRefund`
- Admin-only recovery endpoints: `POST /admin/bookings/{id}/payment/retry`,
  `POST /admin/bookings/{id}/payment/refund` (manual override for support
  cases).

## Daily reconciliation job

No cron/scheduler infrastructure exists yet. Introduce **APScheduler inside
the FastAPI process** (simplest, matches the current single-instance
`backend/docker-compose.yml`; see scaling note below). One job,
`reconcile_booking_payments()`, run once daily:

```
for booking in Bookings.find(status="Active", payment_status != "fully_charged"):
    pct = applicable_refund_percentage(booking.cancellation_policy.rules, days_before_checkin(booking))
    target = booking.total_price * (1 - pct)
    if target > booking.amount_charged + EPSILON:
        charge_off_session(booking, amount=target - booking.amount_charged, reason="scheduled_accrual")
    booking.last_payment_check_at = now()
```

- `charge_off_session` failures split into two cases:
  - `authentication_required` — guest must complete 3DS. Email them a link to
    a small page that mounts Elements against the existing PaymentIntent's
    `client_secret`; set `payment_status = "requires_action"` and surface it
    in the admin panel.
  - `card_declined` / other — set `last_payment_error`, notify the admin, and
    decide a retry policy (e.g. retry next day, cap at N attempts before
    flagging for manual follow-up).
- The job is idempotent by construction (driven off `amount_charged` state,
  safe to re-run), but use a **Stripe idempotency key** per attempt anyway so
  a mid-request crash/retry can't double-charge.
- **Scaling note:** running more than one backend instance would fire this
  job once per instance with in-process APScheduler. At that point, move to a
  dedicated worker/cron container hitting a secured endpoint, or add a
  Mongo-based lock document. Not needed at current scale.

## Cancellation flow update (`POST /bookings/{id}/cancel`)

Currently just flips `status`. Change to:

1. Compute `refund_percentage` as of *now* (the cancellation moment),
   `amount_owed = total_price * (1 - pct)`.
2. If `amount_charged < amount_owed` → one final off-session PaymentIntent
   for the difference (`reason = "cancellation_settlement"`), same code path
   as the daily job.
3. If `amount_charged > amount_owed` (shouldn't happen in normal operation,
   but defensive — e.g. an admin edited the policy rules after the fact) →
   partial refund for the difference.
4. Set `status = "Cancelled"`.

Because the accrual invariant does the work continuously, cancellation almost
never needs an actual Stripe refund — only, at most, one more forfeiture
charge for whatever accrued since the last daily check.

## Currency

Charge in `Booking.currency` (the currency the price was actually quoted in),
**not** `Guest.preferred_currency`. They already coincide in practice — the
guest picks their preferred currency before booking, which determines which
`Price`/`Plan` (and thus which currency) they book against, so
`Booking.currency` *is* the realization of their preference. Don't reconvert
at charge time: the site's FX rates
(`frontend/src/lib/currency-config.ts`) are hardcoded and explicitly not
live, so using them to convert real money would let the Stripe charge diverge
from what the guest actually agreed to pay.

## Frontend touchpoints

- Add `@stripe/stripe-js` + `@stripe/react-stripe-js`; new env var
  `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` (safe to expose).
- In `BookingWidget.tsx`, after booking creation, call
  `POST /bookings/{id}/payment/intent`, mount the Payment Element styled to
  match the existing design, confirm with `stripe.confirmSetup()` /
  `stripe.confirmPayment()`. Treat the webhook-driven `payment_status` as
  truth, not the client-side confirmation result.
- Small recovery page for the `requires_action` email-link case.
- `BookingsPanel.tsx` / `CalendarPanel.tsx`: add a payment-status
  column/badge (`card_verified` / `partially_charged` / `fully_charged` /
  `requires_action` / `failed`) next to the existing status badge.

## Security / PCI notes

- Card data never touches the backend — Stripe.js/Elements sends it directly
  to Stripe; the backend only ever sees tokens (PaymentMethod IDs,
  PaymentIntent/SetupIntent IDs, client secrets). Keeps PCI scope at SAQ A.
- Webhook signature verification is mandatory — reject unsigned/invalid
  requests.
- Idempotency: Stripe idempotency keys on every PaymentIntent-creating call
  from the daily job; dedupe incoming webhooks by Stripe event ID via
  `PaymentEvent`.
- Store only Stripe IDs in MongoDB, never raw card details.

## Env vars

`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` (backend only),
`NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` (frontend, public by design).

## Testing/rollout plan

1. Build against Stripe test mode; use the Stripe CLI (`stripe listen
   --forward-to localhost:8001/webhooks/stripe`) to exercise webhooks locally
   per the repo's end-to-end testing rules (backend on port 8001, a
   dedicated test MongoDB instance, everything torn down after).
2. Unit-test `applicable_refund_percentage` against the same cases already
   covered by the frontend's `refund.ts`, plus the accrual target
   calculation (`total_price × (1 − pct)`) across a multi-rule policy.
3. Exercise the three booking-time paths (free-cancellation SetupIntent,
   partial-fee PaymentIntent, fully-non-refundable PaymentIntent) end-to-end
   with Stripe test cards, including a 3DS-required test card.
4. Simulate the daily job across a policy's rule boundaries (freeze/advance
   the "now" used for `days_before_checkin`) and confirm `amount_charged`
   converges to `total_price` exactly at the 0%-refund boundary, with no
   double-charging on repeated runs.
5. Exercise cancellation at each policy stage (before any charge, mid-accrual,
   fully charged) and confirm the settlement/refund logic matches the
   invariant.
6. Test the off-session failure paths: force `authentication_required`
   (3DS-required saved card) and `card_declined` test cards in the daily job,
   confirm the guest-facing recovery email/page and the admin `requires_action`
   / `failed` surfacing both work.
