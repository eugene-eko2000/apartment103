export const currencies = ["EUR", "CHF", "USD", "GBP"] as const;

export type Currency = (typeof currencies)[number];

export const defaultCurrency: Currency = "EUR";

export const currencySymbols: Record<Currency, string> = {
  EUR: "€",
  CHF: "CHF",
  USD: "$",
  GBP: "£",
};

// No client-side FX math or rate data on purpose — currency conversion is a
// backend-only concern (Stripe FX quotes + commission; see
// backend/app/services/currency_service.py). The domain APIs
// (/prices/public, /bookings/display, /bookings/{id}/display) accept a
// `currency` query param and return already-converted amounts, so this
// module only ever formats numbers it's handed.
export function formatPrice(amount: number, currency: Currency): string {
  const rounded = Math.round(amount);
  return currency === "CHF" ? `${rounded} CHF` : `${currencySymbols[currency]}${rounded}`;
}
