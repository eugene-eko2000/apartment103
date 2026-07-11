export const currencies = ["EUR", "CHF", "USD", "GBP"] as const;

export type Currency = (typeof currencies)[number];

export const defaultCurrency: Currency = "EUR";

export const currencySymbols: Record<Currency, string> = {
  EUR: "€",
  CHF: "CHF",
  USD: "$",
  GBP: "£",
};

// Static reference rates against EUR — this site has no live FX feed.
export const currencyRates: Record<Currency, number> = {
  EUR: 1,
  CHF: 0.95,
  USD: 1.08,
  GBP: 0.86,
};

export function convertFromEur(amountEur: number, currency: Currency): number {
  return amountEur * currencyRates[currency];
}

export function formatPrice(amountEur: number, currency: Currency): string {
  const rounded = Math.round(convertFromEur(amountEur, currency));
  return currency === "CHF" ? `${rounded} CHF` : `${currencySymbols[currency]}${rounded}`;
}
