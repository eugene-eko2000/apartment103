import type { Currency } from "./api";

export interface MatchedRate {
  dailyRate: number; // already converted server-side into `currency`
  dailyRateChf: number; // CHF baseline, for the reference line
  currency: Currency; // the currency `prices` was fetched for (echoed by the API)
}

// Structural shape shared by both Price (admin CRUD, always CHF, no
// daily_rate_chf field) and PublicPrice (/prices/public?currency=..., with
// both daily_rate and daily_rate_chf). Lets these helpers work for either
// without the admin calendar needing to know about currency conversion.
interface RateRangeLike {
  begin_date: string;
  end_date: string;
  daily_rate: number;
  daily_rate_chf?: number;
  min_stay_days: number;
}

interface PriceLike {
  period: {
    currency: Currency;
    date_ranges: RateRangeLike[];
  };
}

function toMatchedRate(range: RateRangeLike, currency: Currency): MatchedRate {
  // Price (admin) has no daily_rate_chf — its daily_rate is already CHF, so
  // that's the correct fallback rather than leaving it undefined.
  return { dailyRate: range.daily_rate, dailyRateChf: range.daily_rate_chf ?? range.daily_rate, currency };
}

// Dates are compared as "yyyy-MM-dd" strings (lexicographic order matches
// chronological order for that format), so callers should format Date
// objects with that pattern before passing them in. begin_date and end_date
// are both inclusive.
export function findDailyRate(prices: PriceLike[], dateStr: string): MatchedRate | null {
  for (const price of prices) {
    for (const range of price.period.date_ranges) {
      if (dateStr >= range.begin_date && dateStr <= range.end_date) {
        return toMatchedRate(range, price.period.currency);
      }
    }
  }
  return null;
}

// Minimum stay (in nights) for a booking starting on dateStr, taken from the
// matched date range's min_stay_days. Defaults to 1 (no constraint) when the
// date falls outside any priced range.
export function findMinStay(prices: PriceLike[], dateStr: string): number {
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
export function findLowestDailyRate(prices: PriceLike[], fromDateStr: string): MatchedRate | null {
  let lowest: MatchedRate | null = null;
  for (const price of prices) {
    for (const range of price.period.date_ranges) {
      if (range.end_date < fromDateStr) continue;
      if (!lowest || range.daily_rate < lowest.dailyRate) {
        lowest = toMatchedRate(range, price.period.currency);
      }
    }
  }
  return lowest;
}
