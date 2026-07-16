import type { Currency, Price } from "./api";

export const FALLBACK_DAILY_RATE = 150;
export const FALLBACK_CURRENCY: Currency = "CHF";

export interface MatchedRate {
  dailyRate: number;
  currency: Currency;
}

// Dates are compared as "yyyy-MM-dd" strings (lexicographic order matches
// chronological order for that format), so callers should format Date
// objects with that pattern before passing them in.
export function findDailyRate(prices: Price[], dateStr: string): MatchedRate | null {
  for (const price of prices) {
    for (const range of price.period.date_ranges) {
      if (dateStr >= range.begin_date && dateStr < range.end_date) {
        return { dailyRate: range.daily_rate, currency: price.period.currency };
      }
    }
  }
  return null;
}
