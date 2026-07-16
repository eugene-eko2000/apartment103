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

export interface Booking {
  _id: string;
  guest: BookingGuestRef;
  booking_date: string;
  currency: Currency;
  date_ranges: BookingDateRange[];
  cancellation_policy: { name: string; rules: CancellationRule[] };
}

export interface BookingInput {
  guest_id: string;
  cancellation_policy_id: string;
  currency: Currency;
  date_ranges: BookingDateRange[];
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

export function requestOtp(identifier: string): Promise<{ message: string }> {
  return request("/auth/otp/request", { method: "POST", body: JSON.stringify({ identifier }) });
}

export function verifyOtp(identifier: string, code: string): Promise<TokenResponse> {
  return request("/auth/otp/verify", { method: "POST", body: JSON.stringify({ identifier, code }) });
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

export function listGuests(token: string): Promise<Guest[]> {
  return request("/guests", { headers: authHeaders(token) });
}

export function createGuest(token: string, data: GuestInput): Promise<Guest> {
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

export { ApiError };
