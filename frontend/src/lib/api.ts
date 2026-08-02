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

export interface BookingDateRange {
  begin_date: string;
  end_date: string;
  price: number;
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

export type BookingStatus = "Active" | "Cancelled";

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
}

export interface BookingRefund {
  stripe_refund_id: string;
  amount: number;
  currency: Currency;
  reason: string;
  created_at: string;
}

export interface BookingWebhookEvent {
  stripe_event_id: string;
  event_type: string;
  data: Record<string, unknown>;
  received_at: string;
}

export interface Booking {
  _id: string;
  guest: BookingGuestRef;
  booking_date: string;
  currency: Currency;
  date_ranges: BookingDateRange[];
  cancellation_policy: { name: string; rules: CancellationRule[] };
  status: BookingStatus;
  stripe_payment_method_id?: string | null;
  payment_status: PaymentStatus;
  amount_charged: number;
  charges: BookingCharge[];
  refunds: BookingRefund[];
  webhook_events: BookingWebhookEvent[];
  last_payment_check_at?: string | null;
  last_payment_error?: string | null;
}

export interface PaymentIntentResponse {
  mode: "setup" | "payment";
  client_secret: string;
  amount: number;
  currency: Currency;
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

export interface BookingInput {
  guest_id: string;
  cancellation_policy_id: string;
  currency: Currency;
  date_ranges: BookingDateRange[];
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

export function requestOtp(identifier: string): Promise<OtpRequestResponse> {
  return request("/auth/otp/request", { method: "POST", body: JSON.stringify({ identifier }) });
}

export function verifyOtp(identifier: string, code: string): Promise<TokenResponse> {
  return request("/auth/otp/verify", { method: "POST", body: JSON.stringify({ identifier, code }) });
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

export function listPublicPrices(): Promise<Price[]> {
  return request("/prices/public");
}

export function listPublicBookedDateRanges(): Promise<BookedDateRange[]> {
  return request("/bookings/public/date-ranges");
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

export function createPaymentIntent(bookingId: string, token: string): Promise<PaymentIntentResponse> {
  return request(`/bookings/${bookingId}/payment/intent`, { method: "POST", headers: authHeaders(token) });
}

export function retryPayment(bookingId: string, token: string): Promise<PaymentIntentResponse> {
  return request(`/bookings/${bookingId}/payment/retry`, { method: "POST", headers: authHeaders(token) });
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
