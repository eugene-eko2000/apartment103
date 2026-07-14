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
  currency: Currency;
  default_price: number;
  date_ranges: { begin_date: string; end_date: string; daily_rate: number }[];
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

export interface Booking {
  _id: string;
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

export function createBooking(
  token: string,
  data: {
    guest_id: string;
    cancellation_policy_id: string;
    currency: Currency;
    date_ranges: BookingDateRange[];
  }
): Promise<Booking> {
  return request("/bookings", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
}

export { ApiError };
