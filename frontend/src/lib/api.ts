import { clearGuestSessionIfToken } from "@/lib/guest-auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Language = "en" | "de" | "fr" | "it";
export type Currency = "EUR" | "CHF" | "USD" | "GBP";
export type SubjectType = "guest" | "admin" | "pending_guest";

export interface ResidenceAddress {
  street_address: string;
  zip: string;
  city: string;
  state?: string | null;
  country: string;
}

export interface Guest {
  _id: string;
  family_name: string;
  first_name: string;
  residence_address: ResidenceAddress;
  phone_number: string;
  email: string;
  preferred_language?: Language | null;
  preferred_currency?: Currency | null;
}

export interface GuestInput {
  family_name: string;
  first_name: string;
  residence_address: ResidenceAddress;
  phone_number: string;
  email: string;
  preferred_language?: Language | null;
  preferred_currency?: Currency | null;
}

export interface CancellationRule {
  days_before_checkin: number;
  refund_percentage: number;
}

export interface Plan {
  _id: string;
  name: string;
  cancellation_policy: { id: string; name: string; rules: CancellationRule[] };
  price_ratio: number;
}

export interface PlanInput {
  name: string;
  cancellation_policy_id: string;
  price_ratio: number;
}

export interface DateRangeRate {
  begin_date: string;
  end_date: string;
  daily_rate: number;
  min_stay_days: number;
}

export interface Period {
  begin_date: string;
  end_date: string;
  currency: Currency;
  date_ranges: DateRangeRate[];
}

export interface Price {
  _id: string;
  period: Period;
}

export interface PriceInput {
  period: Period;
}

// Response shape of GET /prices/public?currency=<Currency> — daily_rate is
// already converted (Stripe FX rate + commission) into the requested
// currency server-side; daily_rate_chf is the stored CHF baseline. No rate
// data is ever exposed, only these two final amounts.
export interface PublicDateRangeRate {
  begin_date: string;
  end_date: string;
  min_stay_days: number;
  daily_rate: number;
  daily_rate_chf: number;
}

export interface PublicPeriod {
  begin_date: string;
  end_date: string;
  currency: Currency;
  date_ranges: PublicDateRangeRate[];
}

export interface PublicPrice {
  _id: string;
  period: PublicPeriod;
}

export type DiscountType = "percent" | "amount";

export interface Promotion {
  _id: string;
  name: string;
  /** Inclusive, like DateRangeRate — not a stay's exclusive checkout day. */
  begin_date: string;
  end_date: string;
  discount_type: DiscountType;
  /** The fraction taken OFF (0.2 = 20% off) — the opposite convention to Plan.price_ratio. */
  discount_ratio: number;
  /** Per night, in `currency`. */
  discount_amount: number;
  currency: Currency;
  /** Gates the discount only; the hard minimum stay is DateRangeRate.min_stay_days. */
  min_stay_days: number;
  active: boolean;
}

export interface PromotionInput {
  name: string;
  begin_date: string;
  end_date: string;
  discount_type: DiscountType;
  discount_ratio: number;
  discount_amount: number;
  currency: Currency;
  min_stay_days: number;
  active: boolean;
}

// Response shape of GET /promotions/public?currency=<Currency> — only
// active, unexpired promotions, with discount_amount already converted
// server-side. Carries no stay price: the calendar tooltip states the offer,
// every actual figure comes from the quote endpoints.
export interface PublicPromotion {
  _id: string;
  name: string;
  begin_date: string;
  end_date: string;
  discount_type: DiscountType;
  discount_ratio: number;
  discount_amount: number;
  discount_amount_chf: number;
  min_stay_days: number;
}

export interface CancellationPolicy {
  _id: string;
  name: string;
  rules: CancellationRule[];
}

export interface CancellationPolicyInput {
  name: string;
  rules: CancellationRule[];
}

export interface Admin {
  _id: string;
  family_name: string;
  first_name: string;
  phone_number: string;
  email: string;
}

export interface AdminInput {
  family_name: string;
  first_name: string;
  phone_number: string;
  email: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  subject_type: SubjectType;
  subject_id: string;
}

export interface GuestSelfRegistrationResponse {
  guest: Guest;
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface GuestCreateResponse {
  guest: Guest;
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

// By-value snapshot of a Promotion as it applied to one booking date range.
// Frozen at booking time: editing or deleting the source promotion never
// changes what an existing booking cost.
export interface AppliedPromotion {
  promotion_id: string | null;
  name: string;
  begin_date: string;
  end_date: string;
  discount_type: DiscountType;
  discount_ratio: number;
  discount_amount: number;
  currency: Currency;
  min_stay_days: number;
  /** Nights of this range the promotion actually discounted. */
  nights: number;
  /** In the BOOKING's currency. */
  discount_total: number;
}

export interface BookingDateRange {
  begin_date: string;
  end_date: string;
  /** The final, discounted amount — what is actually charged. */
  price: number;
  /** The undiscounted amount, for the struck-through line. Display only. */
  regular_price: number;
  applied_promotions: AppliedPromotion[];
}

// Write shape for BookingInput.date_ranges. The guest flow sends dates only:
// the backend prices the stay itself, from the stored nightly rates and the
// ratio of the plan named in `plan_name` (see
// backend/app/services/booking_pricing.py), so a `price` sent alongside a
// plan is ignored outright. `price` exists for the admin editor's
// manual-override flow, which is admin-only and rejected for a guest.
export interface BookingDateRangeInput {
  begin_date: string;
  end_date: string;
  price?: number;
}

// Nested inside a Booking's "guest" Link field, which Beanie serializes with
// an "id" key rather than the "_id" alias used on top-level Guest responses.
export interface BookingGuestRef {
  id: string;
  family_name: string;
  first_name: string;
  email: string;
  phone_number: string;
}

export type BookingStatus = "Pending" | "Active" | "Cancelled";

export type PaymentStatus =
  | "card_verification_pending"
  | "card_verified"
  | "partially_charged"
  | "fully_charged"
  | "requires_action"
  | "failed";

export interface BookingCharge {
  stripe_payment_intent_id: string;
  amount: number;
  currency: Currency;
  reason: "initial_charge" | "scheduled_accrual" | "cancellation_settlement";
  status: "succeeded" | "requires_action" | "failed";
  created_at: string;
  // Stripe's settlement-currency (CHF) view of this charge, read from its
  // balance transaction immediately alongside the payment itself (see the
  // backend's payment_intent.succeeded webhook handler) — null if that
  // fetch never landed (e.g. the balance transaction wasn't available even
  // after retrying, or the charge predates this feature).
  amount_chf?: number | null;
  exchange_rate?: number | null;
  processing_fee_chf?: number | null;
  conversion_fee_chf?: number | null;
  net_amount_chf?: number | null;
}

// A reference, not a copy: the raw Stripe payload lives once on the
// matching PaymentEvent and is fetched on demand via getPaymentEvent (see
// the backend's app/models/booking.py::BookingWebhookEvent).
export interface BookingWebhookEvent {
  stripe_event_id: string;
  event_type: string;
  received_at: string;
}

export interface PaymentEvent {
  _id: string;
  stripe_event_id: string;
  event_type: string;
  processed_at: string;
  booking_id?: string | null;
  data: Record<string, unknown>;
}

export interface BookingChargeScheduleEntry {
  charge_date: string;
  amount: number;
  status: "pending" | "done";
}

export interface Booking {
  _id: string;
  guest: BookingGuestRef;
  booking_date: string;
  currency: Currency;
  date_ranges: BookingDateRange[];
  cancellation_policy: { name: string; rules: CancellationRule[] };
  charge_schedule: BookingChargeScheduleEntry[];
  status: BookingStatus;
  stripe_payment_method_id?: string | null;
  payment_status: PaymentStatus;
  amount_charged: number;
  charges: BookingCharge[];
  webhook_events: BookingWebhookEvent[];
  last_payment_check_at?: string | null;
  last_payment_error?: string | null;
  // When this booking's temporary hold on the dates lapses (ISO 8601), for
  // a Pending booking. Null once it goes Active — a paid booking keeps its
  // dates for good. See the backend's app.services.availability.
  pending_expires_at?: string | null;
}

// Response shape of GET /bookings/{id}/display and GET /bookings/display —
// a currency-converted view of a booking's money fields, computed on
// demand server-side. Lists are index-aligned with the corresponding lists
// on Booking (date_ranges, charges, charge_schedule). Never carries raw
// exchange rates, only final converted amounts (+ their CHF equivalent).
export interface BookingRangeDisplay {
  price: number;
  price_chf: number;
  regular_price: number;
  regular_price_chf: number;
  discount: number;
}

export interface BookingChargeDisplay {
  amount: number;
  amount_chf: number;
}

export interface BookingScheduleDisplay {
  amount: number;
  amount_chf: number;
}

export interface BookingDisplay {
  currency: Currency;
  total_price: number;
  total_price_chf: number;
  total_regular_price: number;
  total_regular_price_chf: number;
  total_discount: number;
  date_ranges: BookingRangeDisplay[];
  charges: BookingChargeDisplay[];
  charge_schedule: BookingScheduleDisplay[];
}

export interface UpcomingCharge {
  charge_date: string;
  amount: number;
}

export interface PaymentIntentResponse {
  mode: "setup" | "payment";
  client_secret: string;
  /** Charged now. Unchanged in meaning by promotions. */
  amount: number;
  /** The stay's full, discounted cost. */
  total_price: number;
  /** Undiscounted, for the struck-through line. Display only. */
  regular_total_price: number;
  total_discount: number;
  currency: Currency;
  upcoming_charges: UpcomingCharge[];
}

/**
 * What became of a payment the guest has just confirmed with Stripe.
 *
 * Stripe answers the browser as soon as the card clears, but the booking is
 * only granted its dates once the backend applies the matching webhook — and
 * that step can still refuse it if another guest paid for the same nights
 * first. "pending" means that answer hasn't arrived yet.
 */
export interface PaymentOutcome {
  state: "pending" | "confirmed" | "conflict" | "failed";
  detail: string | null;
}

// Response shapes of GET /quotes/public… — every figure is computed
// server-side from the same code that prices the booking itself, so the
// widget renders these and multiplies nothing.
export interface QuotePromotion {
  name: string;
  nights: number;
  discount_total: number;
  discount_type: DiscountType;
  discount_ratio: number;
}

export interface PlanQuote {
  plan_id: string;
  plan_name: string;
  price: number;
  regular_price: number;
  discount: number;
  price_per_night: number;
  regular_price_per_night: number;
  price_chf: number;
  regular_price_chf: number;
  applied_promotions: QuotePromotion[];
}

export interface StayQuote {
  currency: Currency;
  nights: number;
  /** The hard minimum stay for this check-in date. */
  min_stay_days: number;
  plans: PlanQuote[];
}

export interface FromPriceQuote {
  currency: Currency;
  price_per_night: number;
  regular_price_per_night: number;
  price_per_night_chf: number;
  regular_price_per_night_chf: number;
  promoted: boolean;
  promotion_name: string | null;
}

export interface BookedDateRange {
  begin_date: string;
  end_date: string;
}

export interface Closure {
  _id: string;
  platform: string;
  begin_date: string;
  end_date: string;
}

export interface ClosureInput {
  platform: string;
  begin_date: string;
  end_date: string;
}

export interface ClosedDateRange {
  begin_date: string;
  end_date: string;
}

export interface ExternalCalendar {
  _id: string;
  name: string;
  /** The other platform's .ics export link, polled by the sync job. */
  url: string;
  /**
   * Path segment of the feed we publish back to that platform
   * (`${API_URL}/calendar/${export_token}.ics`). Unguessable on purpose —
   * an .ics consumer can't send an auth header, so the URL is the
   * credential. Server-generated; never sent on create/update.
   */
  export_token: string;
  last_synced_at: string | null;
  last_sync_status: "ok" | "error" | null;
  last_sync_error: string | null;
  last_sync_block_count: number | null;
}

export interface ExternalCalendarInput {
  name: string;
  url: string;
}

export interface CalendarSyncResult {
  calendar_id: string;
  calendar_name: string;
  status: "ok" | "error";
  created: number;
  updated: number;
  deleted: number;
  error: string | null;
}

// Exactly one of plan_name / cancellation_policy_id is sent, mirroring the
// backend's two shapes (backend/app/schemas/booking.py::BookingCreate):
// the guest flow names the chosen plan and the backend derives both the
// price and the cancellation policy from it; the admin editor names a
// policy directly and sets prices by hand.
export interface BookingInput {
  guest_id: string;
  plan_name?: string;
  cancellation_policy_id?: string;
  currency: Currency;
  date_ranges: BookingDateRangeInput[];
}

export type ImageCategory = string;

export interface Category {
  _id: string;
  slug: string;
  name: string;
  sort_order: number;
  created_at: string;
}

export interface ImageAsset {
  _id: string;
  key: string;
  category: ImageCategory;
  content_type: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  alt: string;
  sort_order: number;
  uploaded_at: string;
  labels: string[];
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });
  if (!response.ok) {
    if (response.status === 401) {
      // The token this call carried is no longer accepted. Drop it here, at
      // the single point every request goes through, so no caller has to
      // remember to — see clearGuestSessionIfToken.
      const authorization = (options.headers as Record<string, string> | undefined)?.Authorization;
      if (authorization?.startsWith("Bearer ")) clearGuestSessionIfToken(authorization.slice(7));
    }
    const body = await response.json().catch(() => null);
    const message = typeof body?.detail === "string" ? body.detail : `Request failed (${response.status})`;
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

export interface OtpRequestResponse {
  message: string;
  retry_after_seconds: number;
}

export function requestOtp(identifier: string, language?: Language): Promise<OtpRequestResponse> {
  return request("/auth/otp/request", { method: "POST", body: JSON.stringify({ identifier, language }) });
}

export function verifyOtp(
  identifier: string,
  code: string,
  audience: "guest" | "admin" = "guest"
): Promise<TokenResponse> {
  return request("/auth/otp/verify", {
    method: "POST",
    body: JSON.stringify({ identifier, code, audience }),
  });
}

export function verifyToken(token: string): Promise<{ status: string }> {
  return request("/auth/token/verify", { headers: authHeaders(token) });
}

export function getGuest(guestId: string, token: string): Promise<Guest> {
  return request(`/guests/${guestId}`, { headers: authHeaders(token) });
}

export function updateGuest(guestId: string, token: string, data: GuestInput): Promise<Guest> {
  return request(`/guests/${guestId}`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
}

export function registerGuestSelf(
  token: string,
  data: GuestInput
): Promise<GuestSelfRegistrationResponse> {
  return request("/guests/self", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
}

export function listPublicPlans(): Promise<Plan[]> {
  return request("/plans/public");
}

export function listPublicPrices(currency: Currency): Promise<PublicPrice[]> {
  return request(`/prices/public?currency=${currency}`);
}

export function listPublicBookedDateRanges(): Promise<BookedDateRange[]> {
  return request("/bookings/public/date-ranges");
}

export function listPublicPromotions(currency: Currency): Promise<PublicPromotion[]> {
  return request(`/promotions/public?currency=${currency}`);
}

/**
 * Every plan's price for one stay, in one request. `signal` lets a caller
 * abort a quote that a faster re-pick has superseded, so an older response
 * can't land after a newer one.
 */
export function getStayQuote(
  beginDate: string,
  endDate: string,
  currency: Currency,
  signal?: AbortSignal
): Promise<StayQuote> {
  return request(
    `/quotes/public?begin_date=${beginDate}&end_date=${endDate}&currency=${currency}`,
    { signal }
  );
}

/** The "from …/night" teaser shown before any dates are picked. */
export function getFromPrice(currency: Currency, signal?: AbortSignal): Promise<FromPriceQuote> {
  return request(`/quotes/public/from?currency=${currency}`, { signal });
}

export function createBooking(token: string, data: BookingInput): Promise<Booking> {
  return request("/bookings", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
}

export function listBookings(token: string): Promise<Booking[]> {
  return request("/bookings", { headers: authHeaders(token) });
}

export function getBooking(bookingId: string, token: string): Promise<Booking> {
  return request(`/bookings/${bookingId}`, { headers: authHeaders(token) });
}

export function updateBooking(bookingId: string, token: string, data: BookingInput): Promise<Booking> {
  return request(`/bookings/${bookingId}`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
}

export function deleteBooking(bookingId: string, token: string): Promise<void> {
  return request(`/bookings/${bookingId}`, { method: "DELETE", headers: authHeaders(token) });
}

export function cancelBooking(bookingId: string, token: string): Promise<Booking> {
  return request(`/bookings/${bookingId}/cancel`, { method: "POST", headers: authHeaders(token) });
}

export function getBookingDisplay(bookingId: string, token: string, currency: Currency): Promise<BookingDisplay> {
  return request(`/bookings/${bookingId}/display?currency=${currency}`, { headers: authHeaders(token) });
}

// Keyed by booking id — lets a bookings list fetch every visible booking's
// converted amounts in one call instead of one request per booking.
export function listBookingsDisplay(
  token: string,
  currency: Currency
): Promise<Record<string, BookingDisplay>> {
  return request(`/bookings/display?currency=${currency}`, { headers: authHeaders(token) });
}

export function createPaymentIntent(bookingId: string, token: string): Promise<PaymentIntentResponse> {
  return request(`/bookings/${bookingId}/payment/intent`, { method: "POST", headers: authHeaders(token) });
}

// Polled between "the card was accepted" and any confirmation being shown —
// see PaymentOutcome. A booking that no longer exists answers "conflict"
// rather than 404ing, so losing a date race reads as an outcome here, not as
// a request that failed.
export function getPaymentOutcome(bookingId: string, token: string): Promise<PaymentOutcome> {
  return request(`/bookings/${bookingId}/payment/outcome`, { headers: authHeaders(token) });
}

export function retryPayment(bookingId: string, token: string): Promise<PaymentIntentResponse> {
  return request(`/bookings/${bookingId}/payment/retry`, { method: "POST", headers: authHeaders(token) });
}

// Resolves one of a booking's webhook_events references to its raw Stripe
// payload. Admin-only.
export function getPaymentEvent(stripeEventId: string, token: string): Promise<PaymentEvent> {
  return request(`/payment-events/${encodeURIComponent(stripeEventId)}`, { headers: authHeaders(token) });
}

export function listGuests(token: string): Promise<Guest[]> {
  return request("/guests", { headers: authHeaders(token) });
}

export function createGuest(token: string, data: GuestInput): Promise<GuestCreateResponse> {
  return request("/guests", { method: "POST", headers: authHeaders(token), body: JSON.stringify(data) });
}

export function deleteGuest(guestId: string, token: string): Promise<void> {
  return request(`/guests/${guestId}`, { method: "DELETE", headers: authHeaders(token) });
}

export function listPlans(token: string): Promise<Plan[]> {
  return request("/plans", { headers: authHeaders(token) });
}

export function getPlan(planId: string, token: string): Promise<Plan> {
  return request(`/plans/${planId}`, { headers: authHeaders(token) });
}

export function createPlan(token: string, data: PlanInput): Promise<Plan> {
  return request("/plans", { method: "POST", headers: authHeaders(token), body: JSON.stringify(data) });
}

export function updatePlan(planId: string, token: string, data: PlanInput): Promise<Plan> {
  return request(`/plans/${planId}`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
}

export function deletePlan(planId: string, token: string): Promise<void> {
  return request(`/plans/${planId}`, { method: "DELETE", headers: authHeaders(token) });
}

export function listPrices(token: string): Promise<Price[]> {
  return request("/prices", { headers: authHeaders(token) });
}

export function getPrice(priceId: string, token: string): Promise<Price> {
  return request(`/prices/${priceId}`, { headers: authHeaders(token) });
}

export function createPrice(token: string, data: PriceInput): Promise<Price> {
  return request("/prices", { method: "POST", headers: authHeaders(token), body: JSON.stringify(data) });
}

export function updatePrice(priceId: string, token: string, data: PriceInput): Promise<Price> {
  return request(`/prices/${priceId}`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
}

export function deletePrice(priceId: string, token: string): Promise<void> {
  return request(`/prices/${priceId}`, { method: "DELETE", headers: authHeaders(token) });
}

export function listPromotions(token: string): Promise<Promotion[]> {
  return request("/promotions", { headers: authHeaders(token) });
}

export function getPromotion(promotionId: string, token: string): Promise<Promotion> {
  return request(`/promotions/${promotionId}`, { headers: authHeaders(token) });
}

export function createPromotion(token: string, data: PromotionInput): Promise<Promotion> {
  return request("/promotions", { method: "POST", headers: authHeaders(token), body: JSON.stringify(data) });
}

export function updatePromotion(
  promotionId: string,
  token: string,
  data: PromotionInput
): Promise<Promotion> {
  return request(`/promotions/${promotionId}`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
}

export function deletePromotion(promotionId: string, token: string): Promise<void> {
  return request(`/promotions/${promotionId}`, { method: "DELETE", headers: authHeaders(token) });
}

export function listCancellationPolicies(token: string): Promise<CancellationPolicy[]> {
  return request("/cancellation-policies", { headers: authHeaders(token) });
}

export function getCancellationPolicy(policyId: string, token: string): Promise<CancellationPolicy> {
  return request(`/cancellation-policies/${policyId}`, { headers: authHeaders(token) });
}

export function createCancellationPolicy(
  token: string,
  data: CancellationPolicyInput
): Promise<CancellationPolicy> {
  return request("/cancellation-policies", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
}

export function updateCancellationPolicy(
  policyId: string,
  token: string,
  data: CancellationPolicyInput
): Promise<CancellationPolicy> {
  return request(`/cancellation-policies/${policyId}`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
}

export function deleteCancellationPolicy(policyId: string, token: string): Promise<void> {
  return request(`/cancellation-policies/${policyId}`, { method: "DELETE", headers: authHeaders(token) });
}

export function listPublicClosedDateRanges(): Promise<ClosedDateRange[]> {
  return request("/closures/public/date-ranges");
}

export function listClosures(token: string): Promise<Closure[]> {
  return request("/closures", { headers: authHeaders(token) });
}

export function getClosure(closureId: string, token: string): Promise<Closure> {
  return request(`/closures/${closureId}`, { headers: authHeaders(token) });
}

export function createClosure(token: string, data: ClosureInput): Promise<Closure> {
  return request("/closures", { method: "POST", headers: authHeaders(token), body: JSON.stringify(data) });
}

export function updateClosure(closureId: string, token: string, data: ClosureInput): Promise<Closure> {
  return request(`/closures/${closureId}`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
}

export function deleteClosure(closureId: string, token: string): Promise<void> {
  return request(`/closures/${closureId}`, { method: "DELETE", headers: authHeaders(token) });
}

export function listExternalCalendars(token: string): Promise<ExternalCalendar[]> {
  return request("/external-calendars", { headers: authHeaders(token) });
}

export function createExternalCalendar(token: string, data: ExternalCalendarInput): Promise<ExternalCalendar> {
  return request("/external-calendars", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
}

export function updateExternalCalendar(
  calendarId: string,
  token: string,
  data: ExternalCalendarInput,
): Promise<ExternalCalendar> {
  return request(`/external-calendars/${calendarId}`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
}

export function deleteExternalCalendar(calendarId: string, token: string): Promise<void> {
  return request(`/external-calendars/${calendarId}`, { method: "DELETE", headers: authHeaders(token) });
}

export function syncExternalCalendar(calendarId: string, token: string): Promise<CalendarSyncResult> {
  return request(`/external-calendars/${calendarId}/sync`, { method: "POST", headers: authHeaders(token) });
}

export function syncAllExternalCalendars(token: string): Promise<CalendarSyncResult[]> {
  return request("/external-calendars/sync", { method: "POST", headers: authHeaders(token) });
}

/** The feed URL to paste into this platform's "sync calendars" setting. */
export function calendarExportUrl(exportToken: string): string {
  return `${API_URL}/calendar/${exportToken}.ics`;
}

export function listAdmins(token: string): Promise<Admin[]> {
  return request("/admins", { headers: authHeaders(token) });
}

export function getAdmin(adminId: string, token: string): Promise<Admin> {
  return request(`/admins/${adminId}`, { headers: authHeaders(token) });
}

export function createAdmin(token: string, data: AdminInput): Promise<Admin> {
  return request("/admins", { method: "POST", headers: authHeaders(token), body: JSON.stringify(data) });
}

export function updateAdmin(adminId: string, token: string, data: AdminInput): Promise<Admin> {
  return request(`/admins/${adminId}`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
}

export function deleteAdmin(adminId: string, token: string): Promise<void> {
  return request(`/admins/${adminId}`, { method: "DELETE", headers: authHeaders(token) });
}

export function imageUrl(key: string): string {
  return `${API_URL}/images/${key}`;
}

export function listImages(category?: ImageCategory): Promise<ImageAsset[]> {
  return request(`/images${category ? `?category=${category}` : ""}`);
}

export async function uploadImage(
  token: string,
  file: File,
  data: { category: ImageCategory; alt: string; sort_order?: number }
): Promise<ImageAsset> {
  const form = new FormData();
  form.append("file", file);
  form.append("category", data.category);
  form.append("alt", data.alt);
  // Omitted (rather than sent as 0) so the backend auto-appends the photo
  // at the end of its category instead of always prepending it.
  if (data.sort_order !== undefined) form.append("sort_order", String(data.sort_order));

  // Not routed through request(): that helper always sends
  // Content-Type: application/json, which would break the multipart
  // boundary the browser sets automatically for a FormData body.
  const response = await fetch(`${API_URL}/images`, {
    method: "POST",
    headers: authHeaders(token),
    body: form,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message = typeof body?.detail === "string" ? body.detail : `Request failed (${response.status})`;
    throw new ApiError(response.status, message);
  }
  return response.json();
}

export function deleteImage(imageId: string, token: string): Promise<void> {
  return request(`/images/${imageId}`, { method: "DELETE", headers: authHeaders(token) });
}

// Public: lets the main site resolve a stable alias (e.g. "hero-current")
// to whichever image currently carries that label, without hardcoding a key.
// `options` lets server components opt out of Next's default fetch caching
// (`{ cache: "no-store" }`) so a label reassignment in the admin panel shows
// up immediately instead of waiting for a rebuild/revalidation.
export function listImagesByLabel(label: string, options?: RequestInit): Promise<ImageAsset[]> {
  return request(`/images/labels/${encodeURIComponent(label)}`, options);
}

export function addImageLabel(imageId: string, token: string, label: string): Promise<ImageAsset> {
  return request(`/images/${imageId}/labels`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ label }),
  });
}

export function removeImageLabel(imageId: string, token: string, label: string): Promise<ImageAsset> {
  return request(`/images/${imageId}/labels/${encodeURIComponent(label)}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
}

export interface ReorderUpdate {
  id: string;
  category: string;
  sort_order: number;
}

export function reorderImages(token: string, updates: ReorderUpdate[]): Promise<ImageAsset[]> {
  return request(`/images/reorder`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ updates }),
  });
}

export function listCategories(token: string): Promise<Category[]> {
  return request("/categories", { headers: authHeaders(token) });
}

export function createCategory(token: string, data: { slug: string; name: string }): Promise<Category> {
  return request("/categories", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
}

export function updateCategory(categoryId: string, token: string, data: { name: string }): Promise<Category> {
  return request(`/categories/${categoryId}`, {
    method: "PATCH",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
}

export function deleteCategory(categoryId: string, token: string): Promise<void> {
  return request(`/categories/${categoryId}`, { method: "DELETE", headers: authHeaders(token) });
}

export { ApiError };
