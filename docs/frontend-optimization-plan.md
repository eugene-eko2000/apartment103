# Frontend optimization plan

Review of `frontend/src` (Next.js 16 App Router + React 19 + Tailwind v4, ~14k LOC excluding lockfile).

**Overall assessment:** the app works and the comments are unusually good — much of what looks strange (the FLIP animation machinery, the `queueMicrotask` deferrals, the `calendarMounted` two-phase unmount) is explained in situ and is load-bearing. The problems are concentrated in three places: **one 1,870-line component** doing far too much, **a hand-copied UI kit** repeated across five modals and six admin panels, and **an 826-line country table** shipped to every visitor that the platform can generate for free.

The single largest measurable win is bundle size (F1); the single largest maintainability win is extracting the shared modal/form/CRUD primitives (F5–F8).

---

## Priority summary

| # | Item | Category | Impact | Effort | Est. LOC |
|---|------|----------|--------|--------|----------|
| F1 | `countries.ts`: 826 lines of data `Intl` already has | Duplication / bundle | **High** | M | **−790** |
| F2 | `BookingWidget.tsx` is 1,870 lines / 20 useState / 6 effects | Overcomplexity | **High** | L | −0 (split) |
| F3 | Re-render storm: every calendar hover recomputes everything | Suboptimal | **High** | M | +20 |
| F4 | `api.ts`: 60 near-identical fetch wrappers | Duplication | Medium | M | **−300** |
| F5 | Admin CRUD panel scaffolding copy-pasted 6× | Duplication | **High** | M | **−350** |
| F6 | `LoginModal` / `BookingModal`: the same OTP flow twice | Duplication | **High** | S | **−180** |
| F7 | Modal shell rebuilt in 5 guest-facing components | Duplication | Medium | S | −120 |
| F8 | `TextField` / `SelectField` defined 3×; guest form built 3× | Duplication | **High** | M | **−280** |
| F9 | `guestToForm` ×3, `LANGUAGES`/`CURRENCIES` ×6, gradient ×16 | Duplication | Medium | S | −60 |
| F10 | `useEscapeKey` / `useOutsideClick` inlined 10× and 6× | Duplication | Medium | S | −70 |
| F11 | Circular dependency: SiteHeader ↔ AmenitiesOverlay | Redundant dependency | Medium | S | ~0 |
| F12 | Whole `Dictionary` passed where a slice would do | Redundant dependency | Medium | S | ~0 |
| F13 | Guest profile fetched 3× independently per page | Suboptimal | Medium | M | −30 |
| F14 | `updateChildAge` mutates state in place | Correctness/hygiene | Low | S | ~0 |
| F15 | `today = new Date()` on every render | Suboptimal | Low | S | ~0 |
| F16 | date-fns locale map duplicated; 4 locales always bundled | Duplication / bundle | Low | S | −10 |
| F17 | Two root layouts duplicate font + theme setup | Duplication | Low | S | −25 |
| F18 | `MyBookingsModal` waterfalls two requests | Suboptimal | Low | S | ~0 |

Net: roughly **−2,200 lines** and a meaningful client-bundle reduction, without changing a single user-visible behaviour.

---

## 1. Redundant and duplicated code

### F1 — `countries.ts` ships 826 lines of data the browser already has

**Where:** [`src/lib/countries.ts`](../frontend/src/lib/countries.ts)

The file contains:
- 198 `{ name, flag }` entries (lines 8–207)
- **three complete translation tables** — de, fr, it — of all 198 country names (lines 223–822), ~600 lines

Every visitor downloads all four languages' worth of country names plus 198 flag emoji, on a page whose booking form uses exactly one of them.

`Intl.DisplayNames` — available in every browser this app supports — produces the same localized names from an ISO 3166-1 alpha-2 code, in *any* locale, at zero bundle cost. Flag emoji are mechanically derivable from the same code via regional indicator symbols:

```ts
const flag = (code: string) =>
  String.fromCodePoint(...[...code.toUpperCase()].map(c => 0x1f1a5 + c.charCodeAt(0)));

const names = new Intl.DisplayNames([locale], { type: "region" });
names.of("CH");   // "Switzerland" | "Schweiz" | "Suisse" | "Svizzera"
```

**The catch, stated plainly:** guest records currently store the **English country name** as the canonical value (`isValidCountry` checks membership in `FLAG_BY_NAME`, and `onChange` emits `c.name`). Two migration paths:

- **(a) Low risk, most of the win.** Keep an English-name → ISO-code map (198 short lines, ~4 KB) and delete the three translation tables and the flag column. `localizedCountryName` becomes `Intl.DisplayNames`, `countryFlag` becomes the codepoint function. Saves ~620 lines and all four locales' translations. **No data migration, no backend change.**
- **(b) Full fix.** Store ISO codes on `Guest.residence_address.country`; the module shrinks to a ~20-line list of codes plus two helpers, and the invoice PDF / emails get correctly-localized country names for free. Requires a backend migration over the `guests` collection.

Recommend **(a) now, (b) when a `guests` migration is happening anyway.**

One behavioural note either way: `Intl.DisplayNames` returns official names, which differ from some of the hand-written ones ("Czechia" vs "Czech Republic", "Congo" vs "Republic of the Congo"). Worth a quick diff before landing, since these strings are guest-visible on invoices.

---

### F5 — Six admin panels are the same 90 lines with different nouns

**Where:** `AdminsPanel` (168), `ClosuresPanel` (159), `PlansPanel` (171), `CancellationPoliciesPanel` (169), `GuestsPanel` (246), `PricesPanel` (217)

Every one of these contains the identical block, character-for-character apart from the noun:

```tsx
const [rows, setRows] = useState<T[]>([]);
const [loading, setLoading] = useState(true);
const [listError, setListError] = useState<string | null>(null);
const [editing, setEditing] = useState<T | null>(null);
const [showModal, setShowModal] = useState(false);
const [form, setForm] = useState<TInput>(emptyForm);
const [formError, setFormError] = useState<string | null>(null);
const [pending, setPending] = useState(false);

const load = () => { listX(token).then(...).catch(err => {
  if (err instanceof ApiError && err.status === 401) return logout();
  setListError(...);
}).finally(() => setLoading(false)); };

useEffect(load, [token]); // eslint-disable-line react-hooks/exhaustive-deps

const openCreate = () => { setEditing(null); setForm(emptyForm); setFormError(null); setShowModal(true); };
const openEdit  = (row) => { setEditing(row); setForm(toForm(row)); setFormError(null); setShowModal(true); };
const handleDelete = async (row) => { if (!window.confirm(...)) return; ... };
const handleBulkDelete = async (rows) => { if (!window.confirm(...)) return; await Promise.all(...); ... };
const handleSubmit = async (e) => { e.preventDefault(); ...editing ? updateX : createX... };
```

That is **8 state hooks and 6 handlers** repeated six times — the `401 → logout()` branch alone appears **24 times**. The `// eslint-disable-line react-hooks/exhaustive-deps` on `useEffect(load, [token])` is repeated six times too, which is a reliable smell that the pattern wants to be a hook.

**Proposal — `useResourceCrud`**

```ts
// src/lib/admin/useResourceCrud.ts
export function useResourceCrud<T, TInput>({
  list, create, update, remove, toForm, emptyForm, label,
}: ResourceConfig<T, TInput>) {
  // owns all 8 state hooks + load/openCreate/openEdit/handleDelete/
  // handleBulkDelete/handleSubmit, including the shared 401→logout rule
  return { rows, loading, listError, editing, showModal, form, setForm,
           formError, pending, openCreate, openEdit, handleDelete,
           handleBulkDelete, handleSubmit, closeModal };
}
```

Each panel then becomes ~50 lines: a `columns` array, an `emptyForm`, a `toForm`, and the modal's form fields. `AdminsPanel` drops from 168 → ~70; `ClosuresPanel` from 159 → ~60.

`BookingsPanel` (471) and `PhotosPanel` (865) keep their own logic but should still use the hook for the shared list/load/401 half.

**Bonus:** centralizing the 401 rule fixes a latent inconsistency — `PhotosPanel.load()` is the one place that *doesn't* check for 401, so an expired admin token there shows a raw error instead of logging out.

---

### F6 — `LoginModal` and `BookingModal` are the same OTP flow, written twice

**Where:** [`src/components/LoginModal.tsx`](../frontend/src/components/LoginModal.tsx) (237), [`src/components/BookingModal.tsx`](../frontend/src/components/BookingModal.tsx) (347)

Compare them side by side: `Step` type, five state hooks, `resetToIdentifier`, `handleRequestOtp`, `handleResendOtp`, the Escape effect, both `<form>` blocks with identical inputs and classNames, and a local `SubmitButton` — all duplicated. The dictionaries duplicate too: `LoginModalDict` is a strict subset of `BookingModalDict` (`identifierTitle`, `identifierHint`, `identifierLabel`, `identifierPlaceholder`, `sendCode`, `otpTitle`, `otpHint`, `otpLabel`, `otpPlaceholder`, `verifyCode`, `resendCode`, `codeResent` — 12 keys, defined twice in **all four** `dictionaries/*.json` files).

They diverge in exactly two ways: what happens after `verifyOtp` succeeds (save a session vs. resolve a full `VerifiedIdentity`), and one button label (`back` vs. `changeIdentifier`).

**Proposal**

```tsx
<OtpFlow
  dict={dict.otp}                    // one shared 12-key dict slice
  lang={lang}
  onVerified={(result) => { /* caller-specific */ }}
  secondaryAction={{ label: dict.back, onClick: resetToIdentifier }}
/>
```

`LoginModal` becomes ~30 lines (modal shell + `saveGuestSession`); `BookingModal` becomes ~70 (modal shell + the guest/admin/pending branch). Saves ~180 lines of TSX and 48 lines of duplicated JSON across the dictionaries.

---

### F7 — The modal shell is rebuilt in five guest-facing components

**Where:** `LoginModal`, `ProfileModal`, `BookingModal`, `MyBookingsModal`, `PrivacyModal` all contain:

```tsx
createPortal(
  <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
       onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
    <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-… max-h-…">
      <div className="px-6 py-4 rounded-t-2xl flex items-center justify-between shrink-0"
           style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}>
        <h2 …>{title}</h2><button aria-label={dict.close}>×</button>
      </div>
      …
```

…plus an identical Escape-key `useEffect`, plus an identical portal-rationale comment. The admin side already solved this — [`src/components/admin/Modal.tsx`](../frontend/src/components/admin/Modal.tsx) is exactly this component — but the guest side never got one.

**Proposal:** add `src/components/Modal.tsx` mirroring the admin one (teal gradient header, `createPortal`, Escape, backdrop-dismiss, optional `footer`, `maxWidth`). Have the five components render `<Modal title=… onClose=… footer=…>`. Consider unifying with the admin `Modal` behind a `tone` prop, the way `CountrySelect` and `PhoneInput` already do — that pattern is established and works.

---

### F8 — `TextField` / `SelectField` exist three times, and the guest form is built three times

**Field primitives.** `TextField` and `SelectField` are defined *locally* at the bottom of [`BookingWidget.tsx:1793-1870`](../frontend/src/components/BookingWidget.tsx) **and** at the bottom of [`ProfileModal.tsx:255-325`](../frontend/src/components/ProfileModal.tsx) — byte-identical implementations — while a third pair lives in [`admin/FormFields.tsx`](../frontend/src/components/admin/FormFields.tsx) differing only in Tailwind palette (teal/gray vs. indigo/slate).

**The form itself.** The "guest details" form — first name, family name, email, phone, street, zip, city, state, country, preferred language, preferred currency — is written out field-by-field in **three** places:
- `BookingWidget.tsx:1533-1600` (11 fields)
- `ProfileModal.tsx:173-231` (11 fields)
- `GuestsPanel.tsx` (11 fields, admin palette)

All three drive the same `GuestInput` shape, all three call `updateAddress`, all three wire `PhoneInput` and `CountrySelect` the same way.

**Proposal**

1. Promote the field primitives to `src/components/fields/` with a `tone: "booking" | "admin"` prop — `CountrySelect` and `PhoneInput` already do precisely this (`TONE_CLASSES`), so this is following an existing convention rather than inventing one.
2. Extract `<GuestFields value={form} onChange={setForm} dict={…} tone={…} locale={lang} />` — one component, three call sites.
3. Extract the shared validity predicate too. `BookingWidget.isGuestDetailsValid` (a 10-clause boolean, lines 583–594) and `ProfileModal`'s much weaker `disabled={pending || !isValidCountry(...)}` should be the same function — right now the booking flow validates thoroughly and the profile editor barely validates at all, which is an inconsistency users can hit.

Estimated saving: ~280 lines, plus the class of bug where a field is added in one place and forgotten in the other two.

---

### F9 — Small constants and helpers scattered across files

| Duplicate | Locations | Fix |
|---|---|---|
| `const LANGUAGES: Language[] = ["en","de","fr","it"]` | `BookingWidget`, `ProfileModal`, `GuestsPanel` | `locales` already exists in `i18n-config.ts` |
| `const CURRENCIES: Currency[] = ["EUR","CHF","USD","GBP"]` | `BookingWidget`, `ProfileModal`, `GuestsPanel`, `PricesPanel`, `BookingsPanel` | `currencies` already exists in `currency-config.ts` |
| `guestToForm(guest)` | `BookingModal:89` (exported), `ProfileModal:45`, `GuestsPanel:36` | one copy in `src/lib/guest.ts`; the `fallbackLang` param makes the exported one a superset already |
| `emptyGuestForm` | `BookingModal:76`, `GuestsPanel:26` | same |
| `linear-gradient(135deg, #0f766e 0%, #0891b2 100%)` | **16 occurrences** as an inline `style` | a `.bg-brand-gradient` utility or `--brand-gradient` CSS var in `globals.css` |
| `Language` / `Currency` types | declared in **both** `api.ts` and `i18n-config.ts`/`currency-config.ts` | pick one; have `api.ts` re-export |

The `Currency` type situation is worth calling out specifically: `api.ts:4` declares `export type Currency = "EUR" | "CHF" | "USD" | "GBP"` and `currency-config.ts:3` derives `export type Currency = (typeof currencies)[number]`. Different files import `Currency` from different modules (`CancellationTimeline` from `currency-config`, `BookingWidget` from `api`). They happen to be structurally identical, so TypeScript never complains — but they will silently diverge the day a currency is added to one list.

---

### F10 — `useEscapeKey` and `useOutsideClick` are inlined everywhere

`document.addEventListener("keydown", …e.key === "Escape"…)` appears in **10 files**; the `mousedown` outside-click pattern in **6** (`CountrySelect`, `UserMenu`, `CurrencySwitcher`, `LanguageSwitcher`, `CalendarPanel`'s `PriceDropdown`, `BookingWidget`). Two five-line hooks in `src/lib/hooks/` replace ~70 lines and, more usefully, give one place to fix accessibility details (e.g. only the topmost modal should respond to Escape — right now with `MyBookingsModal` → `BookingDetailsModal` stacked, one Escape press closes **both**, since both listeners are live on `document`).

That last point is a real, reproducible bug that consolidating the hook makes fixable in one edit.

---

### F4 — `api.ts` is 60 hand-written wrappers over one `request()`

**Where:** [`src/lib/api.ts:404-717`](../frontend/src/lib/api.ts)

Roughly 310 lines of:

```ts
export function listPlans(token: string): Promise<Plan[]> { return request("/plans", { headers: authHeaders(token) }); }
export function getPlan(id: string, token: string): Promise<Plan> { return request(`/plans/${id}`, { headers: authHeaders(token) }); }
export function createPlan(token: string, data: PlanInput): Promise<Plan> { return request("/plans", { method: "POST", headers: authHeaders(token), body: JSON.stringify(data) }); }
export function updatePlan(id: string, token: string, data: PlanInput): Promise<Plan> { … }
export function deletePlan(id: string, token: string): Promise<void> { … }
```

…repeated verbatim for plans, prices, cancellation-policies, closures, admins, guests, categories. Note also the inconsistent argument order — `getPlan(id, token)` but `createPlan(token, data)`, `deleteBooking(bookingId, token)` but `listBookings(token)` — which is a live footgun (both params are `string`, so a swap type-checks).

**Proposal**

```ts
function resource<T, TInput>(path: string) {
  return {
    list:   (token: string) => request<T[]>(path, { headers: authHeaders(token) }),
    get:    (token: string, id: string) => request<T>(`${path}/${id}`, { headers: authHeaders(token) }),
    create: (token: string, data: TInput) => request<T>(path, { method: "POST", headers: authHeaders(token), body: JSON.stringify(data) }),
    update: (token: string, id: string, data: TInput) => …,
    remove: (token: string, id: string) => …,
  };
}

export const plans = resource<Plan, PlanInput>("/plans");
export const prices = resource<Price, PriceInput>("/prices");
// …
```

Seven `resource()` calls replace ~310 lines with ~30, fix the argument-order inconsistency by construction, and slot directly into F5's `useResourceCrud` config. Keep the hand-written functions for the genuinely bespoke endpoints (`/auth/*`, `/bookings/*/payment/*`, `/images` upload, `/bookings/display`).

Also: `uploadImage` duplicates `request()`'s error-handling block verbatim (lines 645–649 vs. 344–348) because it needs to skip the JSON `Content-Type`. Extract a `parseError(response)` helper, or make `request()` detect a `FormData` body and omit the header itself.

---

### F16 — date-fns locale map duplicated, and all four locales always bundled

`const DATE_FNS_LOCALES: Record<Locale, DateFnsLocale> = { en: enUS, de, fr, it }` appears identically in [`BookingWidget.tsx:55`](../frontend/src/components/BookingWidget.tsx) and [`PaymentStep.tsx:15`](../frontend/src/components/PaymentStep.tsx). Move to `i18n-config.ts` (or a `date-locale.ts` to keep `i18n-config` dependency-free).

Separately: this static import pulls **all four** date-fns locales into the client bundle for every visitor, though only one is ever used. Since `lang` is known at the server-component boundary, this could be a dynamic `import()` keyed on the active locale — a modest but free win.

---

### F17 — Two root layouts duplicate the font and theme setup

[`app/[lang]/layout.tsx`](../frontend/src/app/[lang]/layout.tsx) and [`app/admin/layout.tsx`](../frontend/src/app/admin/layout.tsx) both declare `Geist`/`Geist_Mono` with identical config, both render `<html data-theme="light" suppressHydrationWarning className={…}>`, and both inject `THEME_INIT_SCRIPT`. Extract the font declarations to `src/lib/fonts.ts` and the `<html><head>` boilerplate to a shared `<RootHtml>` component. ~25 lines, and it stops the two shells drifting apart.

---

## 2. Overcomplexity

### F2 — `BookingWidget.tsx` is 1,870 lines and holds the entire booking domain

**Where:** [`src/components/BookingWidget.tsx`](../frontend/src/components/BookingWidget.tsx)

It currently owns, in one function component:

- **20 `useState` hooks** + 4 `useRef`s + 2 more refs for FLIP rects
- **6 effects**, two of which are 100+ line `useLayoutEffect` FLIP animation routines with manual `el.style.cssText` mutation, `requestAnimationFrame`, `transitionend` listeners and hand-managed cleanup
- the date-range calendar (react-day-picker config, ~10 predicate functions, 4 modifier closures)
- the guest-count stepper
- the plan/rate chooser
- the full 11-field guest form
- the payment step's host
- session resume from `localStorage`, pending-booking resume, and a `sessionStorage` locale-switch resume handshake
- five embedded sub-components at the bottom (`DateField`, `StaticField`, `Counter`, `TextField`, `SelectField`)
- 15 API function imports

This is the file that will be hardest to change safely, and it is the one most likely to need changing.

**Proposal — extract along the seams that already exist in the code's own comments:**

| Extract | Contents | Est. lines |
|---|---|---|
| `useWidgetFlip.ts` | both `useLayoutEffect` FLIP routines + the ResizeObserver spacer + `pinnedTop`/`pinnedRight` + `captureRect`/`captureCompactRect` | ~280 |
| `useBookingSession.ts` | `resolveSessionIdentity`, `resumeFromSession`, `resumePendingBooking`, the mount-time auto-resume effect, the locale-switch resume handshake | ~180 |
| `AvailabilityCalendar.tsx` | `fetchAvailability`, `isBookedDate`/`isPastDate`/`hasNoPrice`/`isOccupiedDate`/`hasOccupiedBetween`/`isValidCheckout`/`isOccupiedValidCheckout`/`isRangeOrHoverDate`, the `<DayPicker>` block | ~260 |
| `usePlanPricing.ts` | the 14 derived price constants (`pricePerNight` … `chosenPlanRawPrice`) | ~40 |
| `PlanChooser.tsx` | the `visiblePlans.map` rate cards | ~110 |
| `GuestDetailsForm.tsx` | the 11-field form (shared with F8) | ~90 |
| `BookingFooter.tsx` | the 5-branch `footer` ternary | ~110 |

`BookingWidget.tsx` lands around **350 lines** of orchestration — the step machine, the layout shell, and the composition. Each extracted piece becomes independently testable; today the file has no tests at all (`guest-auth.test.ts` is the only test in `src/`).

Do this **after** F3 and F8, so the extraction moves already-improved code rather than needing a second pass.

---

### The FLIP animation machinery specifically

The two `useLayoutEffect` blocks (lines 278–366 and 382–497) are ~220 lines of imperative DOM style mutation. The comments are excellent and each workaround is justified (the Tailwind v4 `translate`-vs-`transform` note, the "clear cssText before measuring" note, the `settle()` gap explanation). This is *not* code to delete casually.

But it is worth evaluating whether the [View Transitions API](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API) — which React 19 and Next 16 both support — expresses this natively. `document.startViewTransition()` plus `view-transition-name` on the widget would replace the whole "freeze rect → force reflow → rAF → animate → transitionend → settle" dance with a browser-managed crossfade-and-morph. That is a spike, not a task: budget a timeboxed prototype, and keep the current code if the result doesn't match the tuned easing curves.

---

## 3. Suboptimal code

### F3 — Every calendar hover re-renders and recomputes the entire widget

**Where:** [`BookingWidget.tsx:120,1080-1120,1225-1260`](../frontend/src/components/BookingWidget.tsx)

`hoverDate` is component-level state, set by `onDayMouseEnter` on **every day cell the mouse crosses**. Each of those state updates re-renders all 1,870 lines' worth of component body, which — because *nothing is memoized* — re-executes:

- `plans.find(...)`, `cheapestPerCancellationFee(plans, …)` (which sorts and fingerprints every plan's rules)
- `findDailyRate(prices, …)`, `findMinStay(prices, …)`, `findLowestDailyRate(prices, …)`
- all 14 derived price constants
- `refundHighlightColor(...)` per visible plan (which builds and merges segment windows)
- the entire `<DayPicker>` element tree with four freshly-allocated `modifiers` closures

And the modifiers are the expensive part: `available`, `past`, `occupiedCheckout` and `unavailable` are each invoked **per day cell** (60 cells across two months), and each one calls `hasNoPrice(date)` → `findDailyRate(prices, …)`, which is a nested loop over every price period × every date range. That is roughly `60 cells × 4 modifiers × O(prices × ranges)` **per mouse-move across a day boundary**.

`isValidCheckout` compounds it: while picking a checkout date it calls `hasOccupiedBetween(from, date)`, which walks day-by-day from check-in and calls `isOccupiedDate` (→ `findDailyRate`) for each intervening night — inside a modifier that already runs 60 times.

**Proposal**

1. Precompute availability **once per `prices`/`bookedRanges` change** into a `Set<string>` of `yyyy-MM-dd` keys:
   ```ts
   const unavailableDays = useMemo(() => buildUnavailableDaySet(prices, bookedRanges), [prices, bookedRanges]);
   ```
   Every `isBookedDate`/`hasNoPrice`/`isOccupiedDate` becomes an O(1) `Set.has(format(date, "yyyy-MM-dd"))`. `hasOccupiedBetween` becomes a prefix-scan over that set.
2. `useMemo` the derived pricing block and `visiblePlans` (F2's `usePlanPricing`).
3. Move `hoverDate` into the extracted `AvailabilityCalendar` so hovering re-renders the calendar only, not the guest form / plan cards / payment host.
4. `useCallback` the modifier predicates so `<DayPicker>` isn't handed four new function identities per render.

This is the change most likely to be *felt* — the calendar currently does measurable work on every mouse-move.

---

### F13 — The guest profile is fetched three times independently

`getGuest(...)` is called from:
- `GuestPreferenceSync` on mount and on every session change ([`GuestPreferenceSync.tsx:20`](../frontend/src/components/GuestPreferenceSync.tsx))
- `BookingModal` after OTP verification ([`BookingModal.tsx:183`](../frontend/src/components/BookingModal.tsx))
- `BookingWidget.resolveSessionIdentity` ([`BookingWidget.tsx`](../frontend/src/components/BookingWidget.tsx)) — plus `verifyToken` immediately before it
- `ProfileModal` on open ([`ProfileModal.tsx:87`](../frontend/src/components/ProfileModal.tsx))

For a logged-in guest who opens the booking widget, that's the same document over the wire 2–3 times on one page. Separately, `readGuestSession()` is called ad-hoc from **7** components, each with its own `queueMicrotask` deferral and its own copy of the "defer so the localStorage read isn't synchronous" comment (`UserMenu`, `MyBookingsModal`, `ProfileModal`, `GuestPreferenceSync`, `BookingWidget`, `admin-auth`).

**Proposal:** a `GuestSessionProvider` (mirroring the existing `AdminAuthProvider`, which already solves exactly this on the admin side) exposing `{ session, guest, ready, refresh, logout }`. It owns the single `getGuest` fetch, the `onGuestSessionChange` subscription, and the microtask deferral. Consumers become `const { guest } = useGuestSession()`. `GuestPreferenceSync` collapses into the provider itself.

This also removes `BookingWidget`'s direct dependency on `guest-auth` and `getGuest` — one fewer of its 15 API imports.

---

### F18 — `MyBookingsModal` waterfalls two requests to render one list

[`MyBookingsModal.tsx`](../frontend/src/components/MyBookingsModal.tsx) fetches `listBookings(token)`, then — gated on `status === "loaded"` — fetches `listBookingsDisplay(token, currency)`, and renders nothing until *both* land (`displaysLoading` blocks the list entirely, showing `dict.loading` twice in sequence). The two calls are independent; they can be `Promise.all`'d, halving perceived latency.

Better still, the backend could fold `display` into the booking list response when a `currency` param is present, removing the second request entirely — the data is computed from the same documents server-side.

---

### F14 — `updateChildAge` mutates existing state objects

**Where:** [`BookingWidget.tsx`](../frontend/src/components/BookingWidget.tsx)

```ts
const updateChildAge = (index: number, age: number | null) => {
  const updated = [...children];
  updated[index].age = age;   // ← mutates the object still referenced by the old array
  setChildren(updated);
};
```

The spread copies the *array*, not the child objects, so this writes through to the object the previous state still holds. It happens to work today (the new array identity triggers the re-render), but it breaks under `StrictMode` double-invocation reasoning, defeats any future `React.memo` on a child row, and is exactly the pattern React 19's compiler assumes you are not doing.

```ts
setChildren(prev => prev.map((c, i) => (i === index ? { ...c, age } : c)));
```

Same fix, and it also removes the stale-closure read of `children`.

---

### F15 — `const today = new Date()` runs on every render

**Where:** [`BookingWidget.tsx:115`](../frontend/src/components/BookingWidget.tsx)

`today` is a fresh `Date` object each render, and it is passed as a prop to `CancellationTimeline` and used in `refundHighlightColor`, `findLowestDailyRate`, `isPastDate` and `cheapestPerCancellationFee`. Combined with F3's hover-driven re-renders, this guarantees prop-identity churn and defeats any memoization added downstream. It also means a session open across midnight silently changes semantics mid-interaction.

`CalendarPanel` already does this correctly (`const today = useMemo(() => new Date(), [])` at line 183) — apply the same treatment here, ideally normalized to start-of-day since only the calendar date matters.

---

## 4. Redundant dependencies between components

### F11 — Circular import: `SiteHeader` → `AmenitiesButton` → `AmenitiesOverlay` → `SiteHeader`

- [`SiteHeader.tsx:3`](../frontend/src/components/SiteHeader.tsx) imports `AmenitiesButton`
- [`AmenitiesButton.tsx:4`](../frontend/src/components/AmenitiesButton.tsx) imports `AmenitiesOverlay`
- [`AmenitiesOverlay.tsx:5`](../frontend/src/components/AmenitiesOverlay.tsx) imports `SiteHeader`

A genuine cycle. It survives because the overlay re-renders `SiteHeader` with an `onCloseAmenities` prop to swap the nav item — a reasonable UI goal reached by an unfortunate route. Cycles like this defeat tree-shaking, can produce `undefined` at module-eval time depending on bundler entry order, and make the dependency graph unreadable.

**Proposal:** invert it. Hoist the amenities open/close state to the page (or a small `OverlayContext`), and let `SiteHeader` receive `amenitiesOpen` / `onToggleAmenities` as props. `AmenitiesOverlay` then renders `{children}` for its header rather than importing `SiteHeader` itself. The cycle disappears and the overlay stops knowing about the header at all.

### F12 — Whole `Dictionary` objects passed where a slice would do

`SiteHeader`, `AmenitiesButton` and `AmenitiesOverlay` all take `dict: Dictionary` — the *entire* 397-key translation object — when each uses a handful of keys. `SiteFooter` does the same.

This couples every one of those components to the full dictionary shape: adding a key anywhere in `en.json` widens their prop type, and it is impossible to tell from a signature what a component actually reads. Every other component in the codebase already does this correctly (`BookingWidget` takes `BookingDict`, `PaymentStep` takes `PaymentStepDict`, `MyBookingsModal` takes `MyBookingsDict`) — the four header/footer components are the outliers.

**Proposal:** declare `SiteHeaderDict`, `AmenitiesDict`, `SiteFooterDict` interfaces the way the rest of the codebase does, and pass slices.

### Other coupling notes

- **`BookingWidget` imports 15 API functions** and 8 components. After F2's extraction, most of those move to the sub-modules that actually use them.
- **`CalendarPanel` imports `findDailyRate`/`findMinStay` from `@/lib/pricing`**, which exists primarily for the guest booking flow. That's fine — `pricing.ts`'s `PriceLike` structural type was deliberately designed to serve both — but it is worth keeping that intent documented, since it's the one place the admin and guest code share a module.
- **`MobileBookingReveal` hardcodes `HEADER_HEIGHT_PX = 64`** to match `page.tsx`'s `h-16`, and `BookingWidget` hardcodes `MOBILE_BREAKPOINT_PX = 1024` to match `lg:`. Both are noted in comments. Promote them to a shared `src/lib/layout-constants.ts` (or CSS custom properties read via `getComputedStyle`) so the JS and the Tailwind classes have one source.

---

## 5. Suggested execution order

**Phase 1 — cheap, isolated, high leverage**
1. F9 shared constants + `guestToForm` (unblocks F8)
2. F10 `useEscapeKey` / `useOutsideClick` hooks — *and fix the stacked-modal Escape bug while you're there*
3. F14, F15 (two-line fixes in `BookingWidget`)
4. F16, F17

**Phase 2 — bundle and shared UI**
5. F1 `countries.ts` via `Intl.DisplayNames` (option **a**)
6. F7 guest-facing `Modal` shell
7. F6 `OtpFlow` extraction
8. F8 field primitives + `GuestFields`

**Phase 3 — data and admin layers**
9. F4 `resource()` factory in `api.ts`
10. F5 `useResourceCrud` across the six panels *(depends on F4)*
11. F13 `GuestSessionProvider`
12. F11, F12 dependency inversion
13. F18

**Phase 4 — the big one**
14. F3 memoization + availability `Set` *(do this before F2)*
15. F2 `BookingWidget` extraction
16. *Spike:* View Transitions API vs. the hand-rolled FLIP

**Testing note.** `src/` currently has exactly one test file (`guest-auth.test.ts`, 76 lines) despite `vitest` and `@playwright/test` both being configured. Phases 2–3 create genuinely unit-testable pure modules (`refund`, `pricing`, `guestToForm`, `buildUnavailableDaySet`, the `resource()` factory) — that is the natural moment to add coverage, and it is what will make Phase 4's extraction safe. Per `AGENTS.md`, run the `visual-eval` skill on each phase before merging, since almost every change above touches rendered output.
