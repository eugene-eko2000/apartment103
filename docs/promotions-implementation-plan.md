# Implementation plan: promotions (discounted booking offers)

## Goal

A **promotion** is a special offer attached to a date range: stays that overlap
it, and are long enough to qualify, get a discount off the regular nightly
price for the overlapped nights. Promotions live in their own MongoDB
collection, are managed from the admin UI, are highlighted in the guest
calendar, and — once a booking is made — are **snapshotted onto the booking**
so its price can never drift when the promotion is later edited or deleted.

Hard constraint carried through the whole design: **every price is computed on
the backend**. The frontend renders numbers the server sent; it never
multiplies a rate by anything.

---

## 1. Rules, stated precisely

The requirements leave a few things open. These are the readings this plan
implements; each is called out so they can be overridden before code is written.

| Question | Decision | Why |
| --- | --- | --- |
| Is `discount_ratio` the *discount* or the *multiplier*? | The **discount fraction**: `0.20` means 20 % off. | The field is named *discount* ratio, and "the largest discount should be chosen" only reads naturally if bigger = cheaper. ⚠️ Note this is the **opposite** convention to `Plan.price_ratio` (a multiplier, `0.85` = pay 85 %) — [plan.py](backend/app/models/plan.py). The admin form will label it "Discount %" and store the fraction. |
| Is `discount_amount` per night or per stay? | **Per night.** | It is described as "deduced from the regular price", and the regular price is a nightly rate; per-night also makes percent and absolute comparable when picking the largest discount. |
| Promotion `end_date`: inclusive? | **Inclusive**, matching `DateRangeRate` in [price.py](backend/app/models/price.py#L10-L15). A stay's *nights* are the half-open `[begin_date, end_date)` interval, so a night `N` is discounted when `promo.begin_date <= N <= promo.end_date`. | Keeps promotion ranges identical in meaning to rate ranges, which the admin already edits with the same calendar widget. |
| Does `min_stay_days` block a booking? | **No.** It only gates whether the discount applies. Availability's hard minimum stay stays `DateRangeRate.min_stay_days`. | A short stay must still be bookable, just at full price. |
| Which nights count towards `min_stay_days`? | The nights of the **booking date range** being priced, not the overlapped subset. | "If the booking fits minimum days requirements **and** overlaps with any promotion date range" — the two conditions are separate. |
| Plan ratio vs. promotion — what order? | `nightly = rate × plan.price_ratio`, **then** the discount. | The plan ratio defines the rate tier the guest chose; the promotion is money off what is actually payable. For percent the order is irrelevant; for an absolute amount, "20 CHF off" should be 20 CHF off the payable price. |
| Which promotion wins when several overlap a night? | The one producing the **largest discount in CHF for that night**, evaluated per night (so a stay can use promotion A for some nights and B for others). | Directly from the requirement, and comparing in CHF makes percent vs. absolute comparable. |
| Can the discount exceed the price? | No — clamped at a nightly price of `0.00`. | `Money` fields are `ge=0`; an un-clamped absolute discount would 500. |
| Currency of `discount_amount` | The promotion carries its own `currency` (default `CHF`), converted through CHF like nightly rates are. | Mirrors `Period.currency`; avoids "20" meaning different money to different guests. |

### The one behavioural change to existing pricing

Today [booking_pricing.py](backend/app/services/booking_pricing.py) charges the
whole stay at the rate matched on its **check-in date**, deliberately (its
module docstring explains why: the quote the guest saw is what they agreed to).
Promotions are inherently per-night, so pricing becomes:

```
base_nightly      = rate(check_in_date) × plan.price_ratio        # unchanged rule
for each night N in [begin_date, end_date):
    discount(N)   = max over eligible promotions of their discount on base_nightly
    nightly(N)    = max(base_nightly − discount(N), 0)
stay_price        = Σ nightly(N)
regular_price     = base_nightly × nights
```

The **base** rate is still the check-in-matched one, so a stay with no
overlapping promotion prices to exactly the same figure it does today — no
regression, no re-pricing of existing behaviour. Only the promotion lookup is
per-night.

Rounding follows the existing convention (`booking_pricing.py` rounds the CHF
daily rate to 2 places *before* multiplying out): the discounted **CHF nightly
rate** is quantised to 2 places, then summed, then converted to the booking
currency. The quote endpoint and the booking-creation path call the *same
function*, so a quote and the booking made from it can never disagree.

---

## 2. Backend

### 2.1 New model — `backend/app/models/promotion.py`

```python
DiscountType = Literal["percent", "amount"]

class Promotion(Document):
    name: str                                   # admin-facing label, shown in the guest tooltip
    begin_date: date                            # inclusive
    end_date: date                              # inclusive
    discount_type: DiscountType
    discount_ratio: float = Field(default=0.0, ge=0.0, le=1.0)   # used when type == "percent"
    discount_amount: Money = Field(default=Decimal("0.00"), ge=0) # used when type == "amount"
    currency: Currency = "CHF"                  # currency of discount_amount
    min_stay_days: int = Field(default=1, ge=1)
    active: bool = True                         # lets an admin park an offer without deleting it

    class Settings:
        name = "promotions"
        indexes = [IndexModel([("begin_date", 1), ("end_date", 1)])]
```

A `model_validator` rejects `end_date < begin_date`, a `percent` promotion with
`discount_ratio == 0`, and an `amount` promotion with `discount_amount == 0`
(both are silent no-ops otherwise).

Register in [mongo.py](backend/app/db/mongo.py) `document_models`.

### 2.2 New migration — `backend/migrations/<ts>_create_promotions_collection.py`

Mirrors [the closures migration](backend/migrations/20260721120000_create_closures_collection.py):
a `free_fall_migration` creating the `(begin_date, end_date)` index, with a
`Backward` that drops it.

### 2.3 Second migration — `<ts>_backfill_booking_regular_price.py`

Existing bookings gain the new display fields: set
`date_ranges.$[].regular_price = date_ranges.$[].price` and
`date_ranges.$[].applied_promotions = []` for every booking. Modelled on
[the booked_nights backfill](backend/migrations/20260821000000_backfill_booking_booked_nights.py).

### 2.4 Booking model changes — `backend/app/models/booking.py`

```python
class AppliedPromotion(BaseModel):
    """By-value snapshot of a Promotion as it applied to one booking date
    range. Never a Link: editing or deleting the source promotion must not
    change the price of a booking that already exists — same rule as
    BookingCancellationPolicy."""
    promotion_id: PydanticObjectId | None      # provenance only; never re-read for pricing
    name: str
    begin_date: date
    end_date: date
    discount_type: DiscountType
    discount_ratio: float
    discount_amount: Money
    currency: Currency
    min_stay_days: int
    nights: int                                # nights of this range it actually discounted
    discount_total: Money                      # in the BOOKING's currency

class BookingDateRange(BaseModel):
    begin_date: date
    end_date: date
    price: Money = Field(ge=0)                 # UNCHANGED: the final, discounted amount
    regular_price: Money = Field(default=Decimal("0.00"), ge=0)   # undiscounted, for the struck-through line
    applied_promotions: list[AppliedPromotion] = Field(default_factory=list)
```

**`price` stays the discounted, payable figure.** That is the whole point of
the shape: `total_price_of`, `build_charge_schedule`, every payment path,
`amount_charged`, the invoice and the cancellation settlement keep working
untouched, because they already read `price`. The new fields are additive and
display-only.

New module-level helpers next to `total_price_of`:
`total_regular_price_of(date_ranges)` and
`total_discount_of(date_ranges) = regular − price`, plus matching
`Booking.total_regular_price` / `Booking.total_discount` properties.

### 2.5 Pricing service — rewrite of `backend/app/services/booking_pricing.py`

The current `price_date_ranges` becomes a thin wrapper over a new, shared
quoting core so that **the quote endpoint and booking creation cannot drift**:

```python
@dataclass
class NightBreakdown:
    night: date
    regular_chf: Decimal
    price_chf: Decimal
    promotion: Promotion | None

@dataclass
class RangeQuote:
    begin_date: date
    end_date: date
    nights: int
    regular_price: Decimal        # in the requested currency
    price: Decimal
    discount: Decimal
    regular_price_chf: Decimal
    price_chf: Decimal
    applied_promotions: list[AppliedPromotion]

async def quote_ranges(
    ranges: list[BookingDateRangeInput], ratio: Decimal, currency: Currency
) -> list[RangeQuote]: ...
```

Algorithm per range:

1. `matched = _match_rate(prices, range.begin_date)` — unchanged; raises
   `UnpricedDatesError` when nothing covers the check-in date.
2. `base_chf = to_decimal(convert(rate.daily_rate → CHF) × ratio)`.
3. `nights = (end_date − begin_date).days`.
4. For each night `N`:
   `eligible = [p for p in promotions if p.active and p.begin_date <= N <= p.end_date and nights >= p.min_stay_days]`
   `discount_chf(p) = base_chf × Decimal(str(p.discount_ratio))` for `percent`,
   or `convert(p.discount_amount, p.currency → CHF)` for `amount`;
   both quantised to 2 places and clamped to `[0, base_chf]`.
   Take the `max`; ties break on the earliest `begin_date` then `_id`, so the
   choice is deterministic and reproducible between quote and booking.
5. Sum the nightly CHF figures; convert the range totals into `currency`
   (`convert_amount_with_rates`, one rate table fetched for the whole call —
   sources = every price currency ∪ every promotion currency ∪ `{"CHF"}`).
6. Group the chosen promotions into `AppliedPromotion` entries (one per
   distinct promotion, with its night count and summed discount).

`price_date_ranges(...)` then maps `RangeQuote` → `BookingDateRange`
(`price`, `regular_price`, `applied_promotions`), and
[bookings.py `_resolve_terms`](backend/app/api/routes/bookings.py#L67-L118)
needs no change at all — it already calls that one function for the guest path.

The admin manual-override path (`cancellation_policy_id`, prices taken
verbatim) sets `regular_price = price` and `applied_promotions = []`: an admin
typing a final amount is stating the actual figure, promotions included.

**No promotion id is ever accepted from the client.** The requirement mentions
possibly wiring a promotion id through the booking process; this plan
deliberately does not, for the same reason `price` is ignored on the guest path
today — a client-supplied promotion id is a client-supplied discount. The
server re-resolves promotions from the database at booking time, exactly as the
quote endpoint did seconds earlier, from the same dates and the same code.

### 2.6 New route module — `backend/app/api/routes/promotions.py`

Admin CRUD through the existing factory
([crud.py](backend/app/api/crud.py)) — `Promotion` is a genuinely uniform
resource, so no hand-written handlers:

```python
router = make_crud_router(
    model=Promotion, create_schema=PromotionCreate, prefix="/promotions",
    noun="Promotion", id_param="promotion_id", tags=["promotions"],
    dependencies=[Depends(require_admin)], sort="begin_date",
)
```

Plus an unauthenticated public router, mounted **before** it in
[main.py](backend/app/main.py) (same pattern as prices/closures):

`GET /promotions/public?currency=EUR` → `list[PublicPromotion]`

```jsonc
{
  "_id": "…", "name": "Spring escape",
  "begin_date": "2026-04-01", "end_date": "2026-04-20",
  "discount_type": "percent",
  "discount_ratio": 0.2,              // percent promotions only
  "discount_amount": 0,               // converted into `currency` for amount promotions
  "discount_amount_chf": 0,
  "min_stay_days": 4
}
```

Only `active` promotions whose `end_date >= today` are returned. This feeds the
calendar highlight + tooltip. It carries no computed stay price — the tooltip
states the offer ("20 % off, 4 nights minimum"), not a total.

### 2.7 New route module — `backend/app/api/routes/quotes.py`

The answer to "how do we price a booking that doesn't exist yet".

**`GET /quotes/public?begin_date=&end_date=&currency=`** → `StayQuote`

```jsonc
{
  "currency": "EUR",
  "nights": 5,
  "min_stay_days": 3,                 // the hard minimum for this check-in date
  "plans": [
    {
      "plan_id": "…", "plan_name": "Flexible",
      "price": 640.00,                // discounted total, what will be charged
      "regular_price": 800.00,        // undiscounted, for the struck-through line
      "discount": 160.00,
      "price_per_night": 128.00,
      "regular_price_per_night": 160.00,
      "price_chf": 610.00, "regular_price_chf": 762.00,
      "applied_promotions": [
        { "name": "Spring escape", "nights": 5, "discount_total": 160.00,
          "discount_type": "percent", "discount_ratio": 0.2 }
      ]
    }
  ]
}
```

One request returns every plan's numbers, so the plan-selection step needs no
per-plan round trip. Implemented by calling `quote_ranges` once per plan ratio
against a single pre-fetched price/promotion/rate snapshot.

**`GET /quotes/public/from?currency=`** → the "from CHF 150 / night" teaser
shown before any dates are picked:

```jsonc
{ "currency": "EUR", "price_per_night": 120.00, "regular_price_per_night": 150.00,
  "price_per_night_chf": 114.00, "regular_price_per_night_chf": 142.50,
  "promoted": true, "promotion_name": "Spring escape" }
```

Computed server-side as the cheapest future nightly rate × the cheapest plan
ratio, with the best promotion applicable on that rate's range — replacing
`findLowestDailyRate` arithmetic on the client.

### 2.8 Display endpoints — `backend/app/schemas/booking.py` + `bookings.py`

`BookingDisplay` gains the discounted-vs-regular pair so the details pages need
no arithmetic:

```python
class BookingRangeDisplay(BaseModel):
    price: Money
    price_chf: Money
    regular_price: Money            # new
    regular_price_chf: Money        # new
    discount: Money                 # new

class BookingDisplay(BaseModel):
    ...
    total_regular_price: Money      # new
    total_regular_price_chf: Money  # new
    total_discount: Money           # new
```

`BookingDisplaySource`'s projection must add the new fields (it already
projects `date_ranges`, so only `total_regular_price` derivation is new).
`_build_display` converts them against the same single rate table it already
fetches.

`PaymentIntentResponse` ([schemas/payment.py](backend/app/schemas/payment.py))
gains `regular_total_price` and `total_discount`, so the payment step can show
the saving. `amount` / `total_price` keep meaning exactly what they mean today
(the discounted, charged figures) — no payment logic changes.

### 2.9 Emails / invoice

[invoice.py](backend/app/services/invoice.py) and the booking emails read
`booking.total_price` / `date_ranges[].price`, which are already the discounted
figures, so they stay correct with no change. **Optional (recommended)
follow-up in the same PR:** add a "Regular price / You saved" line to the
booking-confirmation email and the charge invoice when
`booking.total_discount > 0`, using the stored snapshot. Templates live in
`backend/data/<lang>/` and need all four languages.

### 2.10 Backend tests

* `backend/tests/test_booking_pricing_promotions.py` (new) — the algorithm:
  no overlap → price identical to today; partial overlap → only overlapped
  nights discounted; `min_stay_days` not met → no discount; percent vs.
  absolute; two overlapping promotions → larger discount per night wins, and a
  stay can mix both across its nights; absolute discount larger than the rate →
  clamped to 0, never negative; promotion in a non-CHF currency; `active=False`
  ignored.
* `backend/tests/api/test_promotions.py` (new) — CRUD auth (admin only, 401/403
  like [test_prices.py](backend/tests/api/test_prices.py)), validation errors,
  the public endpoint hiding inactive/expired promotions and converting
  currency.
* `backend/tests/api/test_quotes.py` (new) — quote matches, to the cent, the
  `date_ranges[].price` of a booking then created for the same dates/plan.
  This is the anti-drift regression test.
* `backend/tests/api/test_bookings.py` — extend: a booking created over a
  promoted range stores `regular_price` and a populated `applied_promotions`,
  and the stored copy is unaffected by afterwards editing or deleting the
  source promotion.
* `backend/tests/test_charge_schedule.py` — assert the schedule sums to the
  **discounted** total.

---

## 3. Frontend

### 3.1 `frontend/src/lib/api.ts`

Add types `Promotion`, `PromotionInput`, `PublicPromotion`, `AppliedPromotion`,
`StayQuote`, `PlanQuote`, `FromPriceQuote`; extend `BookingDateRange`,
`BookingRangeDisplay`, `BookingDisplay`, `PaymentIntentResponse`. Add
`listPromotions/getPromotion/createPromotion/updatePromotion/deletePromotion`
(admin), `listPublicPromotions(currency)`, `getStayQuote(begin, end, currency)`,
`getFromPrice(currency)`.

### 3.2 `frontend/src/lib/pricing.ts` — price math deleted

`findDailyRate` / `findLowestDailyRate` exist purely to multiply rates on the
client and must go from the guest flow. What remains is **availability**
logic, which is legitimately client-side:

* `hasRateFor(prices, dateStr): boolean` — replaces `findDailyRate(...) !== null`
  in `hasNoPrice` (calendar disabling).
* `findMinStay(prices, dateStr)` — unchanged.

`/prices/public` stays as it is (the admin calendar and these helpers use it);
dropping the now-unused `daily_rate` fields from its response is an optional
tidy-up, not part of this change.

### 3.3 `frontend/src/components/BookingWidget.tsx`

**Pricing state.** Replace the ~10 derived `const price… = rate × ratio × nights`
lines ([BookingWidget.tsx:539-572](frontend/src/components/BookingWidget.tsx#L539-L572))
with:

```ts
const [quote, setQuote] = useState<StayQuote | null>(null);
const [fromPrice, setFromPrice] = useState<FromPriceQuote | null>(null);
```

* `fromPrice` — fetched once per `currency` change; drives the "from …/night" header.
* `quote` — fetched (debounced ~150 ms, with an AbortController so a fast
  re-pick can't land out of order) whenever `range.from && range.to && currency`
  changes; cleared while in flight so the existing `LoadingSpinner` shows
  instead of a stale figure.

Every price the widget renders — header, per-plan card, per-night line, total —
comes from `quote.plans[i]` / `fromPrice`. `formatPrice` still formats; nothing
multiplies.

**Struck-through regular price.** A small shared component
`frontend/src/components/PriceWithDiscount.tsx`:

```tsx
<PriceWithDiscount price={p.price} regularPrice={p.regular_price} currency={currency} size="lg" />
// renders: <s class="text-gray-400 dark:text-gray-500 text-[0.8em] mr-2">CHF 800</s> <b>CHF 640</b>
// and nothing but the plain price when regular_price <= price
```

Used in the plan cards, the widget header, the summary total, `PaymentStep`,
`BookingDetailsModal` and `MyBookingsModal`, so the treatment is identical
everywhere and defined once.

**Calendar highlighting.** `listPublicPromotions(currency)` is fetched in the
same effect that loads booked/closed ranges. New helper
`promotionsForDate(promotions, dateStr): PublicPromotion[]`, and a new
`DayPicker` modifier alongside the existing `available` / `unavailable` /
`occupiedCheckout` set
([BookingWidget.tsx:1171-1201](frontend/src/components/BookingWidget.tsx#L1171-L1201)):

```ts
promoted: (date) => !isRangeOrHoverDate(date) && !isPastDate(date)
  && !isOccupiedDate(date) && !isInvalidCheckoutCandidate(date)
  && promotionsForDate(promotions, format(date, "yyyy-MM-dd")).length > 0,
```

listed **before** `available` so a promoted free day takes the promotion tint
rather than the green one (`available` gets `&& !isPromotedDate(date)`).

Colour — the palette already uses green = available, red = unavailable,
yellow = occupied-but-checkout-able, teal = selection, grey = past. **Violet**
is the only unclaimed, unambiguous slot:

```ts
promoted: "!bg-violet-100 dark:!bg-violet-950/50 !text-violet-800 dark:!text-violet-300 " +
          "hover:!bg-violet-200 dark:hover:!bg-violet-900/60 !font-semibold"
```

**Tooltip.** `react-day-picker` has no tooltip API, and a native `title`
attribute has a ~1 s delay and no styling. Render a custom day button via
`components={{ DayButton }}`, wrapping the default button in a
`relative group` span with an absolutely-positioned tooltip shown on
`group-hover` / `focus-within`:

> **Spring escape** — 20 % off · min. 4 nights
> (absolute type: **Spring escape** — CHF 30 off per night · min. 4 nights)

Multiple promotions on one day list one line each. The same text also goes on a
`title` attribute and an `aria-label`, so touch devices and screen readers get
it. The tooltip is `pointer-events-none`, `z-50`, flips to render below the day
for the first calendar row.

**Legend.** The calendar has no legend today; add a violet swatch + "Special
offer" only if a legend is introduced — otherwise the tooltip carries it.

### 3.4 Other guest surfaces

* [PaymentStep.tsx](frontend/src/components/PaymentStep.tsx#L152-L172) — show
  `PriceWithDiscount` for the total and a "You save {amount}" line when
  `intent.total_discount > 0`. `intent.amount` (what is being charged now)
  keeps its current single-figure rendering.
* [BookingDetailsModal.tsx](frontend/src/components/BookingDetailsModal.tsx#L183-L220)
  — per-range and total lines become `PriceWithDiscount` using
  `display.date_ranges[i].regular_price` / `display.total_regular_price`; a
  promotion line ("Spring escape — 5 nights, −CHF 160") is listed from
  `booking.date_ranges[i].applied_promotions`. The cancellation timeline keeps
  using `display.total_price` (the discounted figure) — refunds are computed
  off what the guest actually pays.
* [MyBookingsModal.tsx](frontend/src/components/MyBookingsModal.tsx#L211-L230)
  — same treatment for the per-range and total lines.
* [BookingsPanel (admin)](frontend/src/components/admin/resources/BookingsPanel.tsx)
  — add a "Discount" column and show the promotion snapshot in the booking
  detail view, so an admin can see why a booking is cheaper than the rate card.

### 3.5 Admin promotions page

* `AdminShell` — add `"promotions"` to `AdminTab` and `{ id: "promotions", label: "Promotions" }`
  to `TABS`, placed right after `"prices"` ([AdminShell.tsx](frontend/src/components/admin/AdminShell.tsx#L5-L29)).
* `app/admin/page.tsx` — `{tab === "promotions" && <PromotionsPanel />}`.
* **`frontend/src/components/admin/resources/PromotionsPanel.tsx`** (new) —
  built exactly like [ClosuresPanel](frontend/src/components/admin/resources/ClosuresPanel.tsx):
  `DataTable` + `Modal` + `FormFields`, with list/create/edit/delete/bulk-delete
  and the shared 401 → `logout()` handling.
  * Columns: Name · Dates (`begin – end`) · Discount (`20 %` or `CHF 30 / night`)
    · Min stay · Active.
  * Form: `TextField` name; `DateRangeCalendarField` for the range (reusing
    [the same component the price editor uses](frontend/src/components/admin/DateRangeCalendarField.tsx),
    with `blockedRanges=[]` — promotions are allowed to overlap each other, that
    is what "largest discount wins" is for); `SelectField` discount type;
    then **conditionally** a `NumberField` "Discount %" (0–100, stored ÷ 100) for
    `percent`, or `NumberField` "Discount amount" + `SelectField` currency for
    `amount`; `NumberField` "Minimum stay (nights)"; a checkbox for `active`.
  * Client-side guards before submit: end ≥ begin, and a non-zero discount for
    the selected type (the backend validates the same, this is just a nicer
    error).
  * Deleting a promotion warns that it does **not** change bookings already
    made — their snapshot governs.

### 3.6 i18n

New keys in all four of
[en](frontend/src/app/[lang]/dictionaries/en.json)/de/fr/it, under `booking`:

```
specialOffer            "Special offer"
regularPrice            "Regular price"
youSave                 "You save {amount}"
promotionPercentTooltip "{name} — {percent}% off · min. {nights} nights"
promotionAmountTooltip  "{name} — {amount} off per night · min. {nights} nights"
promotionApplied        "{name} — {nights} nights, −{amount}"
```

and the corresponding fields on `BookingDict` / `PaymentStepDict` /
`BookingDetailsDict`. Admin UI stays English, like the rest of it.

---

## 4. Order of work

1. **Backend model + migrations + admin CRUD + public promotions endpoint**,
   with `test_promotions.py`. Nothing else observes promotions yet — shippable
   and inert on its own.
2. **Pricing core**: `quote_ranges`, `price_date_ranges` rewritten on top of it,
   `BookingDateRange.regular_price` / `applied_promotions`, backfill migration,
   `test_booking_pricing_promotions.py`. Bookings now price with promotions;
   the widget still shows its own (now possibly higher) numbers, so this and
   step 3 land together.
3. **Quote endpoints** + `test_quotes.py` (including the quote-equals-booking
   assertion).
4. **Display plumbing**: `BookingDisplay` / `PaymentIntentResponse` fields.
5. **Frontend**: `api.ts` types, `pricing.ts` trim, `PriceWithDiscount`,
   `BookingWidget` switched to server quotes, calendar highlight + tooltip.
6. **Frontend**: details/my-bookings/payment-step discounted rendering, i18n.
7. **Admin**: `PromotionsPanel`, tab wiring, bookings-panel discount column.
8. **Docs**: append an "as built" section here, like
   [calendar-sync-design.md](docs/calendar-sync-design.md) does.

Steps 2–3 must ship together; steps 5–7 are independently reviewable.

---

## 5. Verification

Per [AGENTS.md](AGENTS.md), every change is verified end-to-end with the
**visual-eval** skill (base = `main`, eval = this branch), and the annotated
result images are reported. Scenarios to capture:

1. Open the booking widget → calendar shows violet promoted days; hover one →
   tooltip with discount and minimum stay.
2. Pick dates fully inside a promotion → plan cards show discounted total with
   the regular price struck through.
3. Pick dates only partly overlapping → discount reflects the overlapped nights
   only.
4. Pick a stay shorter than `min_stay_days` → no discount, regular price only
   (and no struck-through line).
5. Complete the flow to the payment step → discounted total + "You save".
6. Open a completed booking's details → discounted prices, promotion line,
   regular price struck through.
7. Admin → Promotions: create, edit, delete a promotion.
8. Switch display currency mid-flow → all figures re-fetched from the server
   and consistent.

Backend: `pytest backend/tests` — the whole existing suite must stay green,
since a stay with no promotion is required to price exactly as it did before.

---

## 6. Implementation notes (as built)

Everything in sections 1–5 was implemented as specified. What follows is
only where the code says something the plan left open, plus the one place
the plan's own wording had to be resolved.

### Where the pieces landed

| Plan | File |
| --- | --- |
| §2.1 model | [promotion.py](backend/app/models/promotion.py), registered in [mongo.py](backend/app/db/mongo.py) |
| §2.2 / §2.3 migrations | `20260825120000_create_promotions_collection.py`, `20260825120100_backfill_booking_regular_price.py` |
| §2.4 booking model | [booking.py](backend/app/models/booking.py) — `AppliedPromotion`, `regular_price`, `total_regular_price_of`, `total_discount_of` |
| §2.5 pricing core | [booking_pricing.py](backend/app/services/booking_pricing.py) |
| §2.6 promotions routes | [promotions.py](backend/app/api/routes/promotions.py), [schemas/promotion.py](backend/app/schemas/promotion.py) |
| §2.7 quote routes | [quotes.py](backend/app/api/routes/quotes.py), [schemas/quote.py](backend/app/schemas/quote.py) |
| §3.x frontend | `PriceWithDiscount.tsx`, `PromotionsPanel.tsx`, and edits to `BookingWidget`, `PaymentStep`, `BookingDetailsModal`, `MyBookingsModal`, `BookingsPanel`, `pricing.ts`, `api.ts` |

### Decisions the plan left to the implementation

* **`quote_ranges` is split in three.** §2.7 asks for one snapshot shared
  across every plan in a stay quote, while §2.5 specifies `quote_ranges` as
  a self-contained `async` call. Both exist: `load_pricing_snapshot` reads
  prices/promotions/rates once, the synchronous `quote_ranges_with` prices
  against a snapshot, and `quote_ranges` is the one-shot wrapper with
  exactly the signature §2.5 gives. `price_date_ranges` uses the wrapper;
  the quote endpoint uses the snapshot form.
* **Validation lives in two places on purpose.** The consistency rules
  (§2.1) are a shared `validate_promotion_fields` applied by both the
  `Promotion` document and the `PromotionCreate` schema, so a bad payload
  is a 422 from request validation rather than a 500 raised while building
  the model.
* **`AppliedPromotion`s are grouped by object identity**, not by
  `promotion_id`: every night of one quote resolves against the same
  snapshot list, so the same promotion is literally the same object — and
  this stays correct for a promotion that has no id yet.
* **`findDailyRate` survives in `pricing.ts`.** §3.2 removes client price
  math *from the guest flow*; the admin calendar
  ([CalendarPanel](frontend/src/components/admin/resources/CalendarPanel.tsx))
  legitimately prints the configured rate card, and §3.2 itself notes that
  `/prices/public` stays for it. `findLowestDailyRate` is gone, and
  `hasRateFor` / `promotionsForDate` are new.
* **The widget derives quote staleness instead of clearing it.** §3.3 says
  to clear `quote` while a request is in flight. Storing the quote together
  with the dates and currency it was fetched for gets the same result — a
  quote that no longer matches the selection reads as absent, so the
  spinner shows — without a `setState` in an effect body, which this
  project's lint rules reject.
* **A promotion line is labelled in the booking's currency.**
  `AppliedPromotion.discount_total` is denominated in the *booking's*
  currency (§2.4), and no amount is ever converted on the client — so
  `BookingDetailsModal` prints it as e.g. "−360 CHF" even when the display
  currency is EUR. The converted saving is the separate "You save" line,
  which the server computes.
* **§2.9 was done, not skipped.** The confirmation email and the charge
  invoice gained a "Regular price / You save" block, in all four languages,
  shown only when `total_discount > 0`.

### Verification

`pytest backend/tests`: **523 passed**, including the 18 new algorithm
tests, 27 promotion CRUD/public tests, 12 quote tests (with the
quote-equals-booking anti-drift assertion), 6 booking-snapshot tests and 2
charge-schedule tests asserting the schedule follows the *discounted* total.
The pre-existing suite is unchanged and green: a stay with no overlapping
promotion prices to exactly the figure it did before.

Frontend: `tsc --noEmit` clean, `next build` succeeds, `vitest` green, and
`eslint` reports the same three pre-existing `set-state-in-effect` errors in
`BookingWidget.tsx` as `main` — no new ones.

End-to-end, per [AGENTS.md](AGENTS.md), with the visual-eval skill (base =
`main`, eval = this branch). Annotated results in
[evals/2026-08-25_235826](evals/2026-08-25_235826):

| Scenario | Image |
| --- | --- |
| Widget on load — "from" teaser discounted | `step1_widget_annotated.png` |
| Calendar — violet promoted days | `step2_calendar_annotated.png` |
| Hover a promoted day — offer tooltip | `step3_tooltip_annotated.png` |
| 4-night stay inside a promotion | `step4_discounted_stay_annotated.png` |
| 2-night stay below `min_stay_days` — no discount | `step5_below_min_stay_annotated.png` |
| 6-night stay spanning two offers | `step6_partial_overlap_annotated.png` |
| Currency switched mid-flow | `step7_currency_eur_annotated.png` |
| Admin tab bar / Promotions list / promotion form | `step8_`, `step9_`, `step10_…_annotated.png` |
| Admin create → edit → delete round trip | `crud1_`…`crud4_*.png` |
| My bookings + booking details, discounted | `step11_`, `step12_…_annotated.png` |

Two of §5's scenarios could not be captured: the payment step's "You save"
line and reaching a booking through checkout both require live Stripe
credentials, which this machine has none of. The payment step's rendering is
covered by `PaymentIntentResponse`'s new fields being asserted server-side;
the booking-details surfaces were exercised against an Active booking seeded
directly into MongoDB in exactly the shape the booking endpoint writes.
