import type { Currency, Price } from "./api";

export const FALLBACK_DAILY_RATE = 150;
export const FALLBACK_CURRENCY: Currency = "CHF";

export interface MatchedRate {
  dailyRate: number;
  currency: Currency;
}

// Dates are compared as "yyyy-MM-dd" strings (lexicographic order matches
// chronological order for that format), so callers should format Date
// objects with that pattern before passing them in. begin_date and end_date
// are both inclusive.
export function findDailyRate(prices: Price[], dateStr: string): MatchedRate | null {
  for (const price of prices) {
    for (const range of price.period.date_ranges) {
      if (dateStr >= range.begin_date && dateStr <= range.end_date) {
        return { dailyRate: range.daily_rate, currency: price.period.currency };
      }
    }
  }
  return null;
}

// Minimum stay (in nights) for a booking starting on dateStr, taken from the
// matched date range's min_stay_days. Defaults to 1 (no constraint) when the
// date falls outside any priced range.
export function findMinStay(prices: Price[], dateStr: string): number {
  for (const price of prices) {
    for (const range of price.period.date_ranges) {
      if (dateStr >= range.begin_date && dateStr <= range.end_date) {
        return range.min_stay_days;
      }
    }
  }
  return 1;
}

// Used as the "from" rate shown before any dates are picked. Ranges that
// have already fully elapsed (end_date < fromDateStr) are excluded so past
// pricing never surfaces as the lowest rate.
export function findLowestDailyRate(prices: Price[], fromDateStr: string): MatchedRate | null {
  let lowest: MatchedRate | null = null;
  for (const price of prices) {
    for (const range of price.period.date_ranges) {
      if (range.end_date < fromDateStr) continue;
      if (!lowest || range.daily_rate < lowest.dailyRate) {
        lowest = { dailyRate: range.daily_rate, currency: price.period.currency };
      }
    }
  }
  return lowest;
}
