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

/**
 * The rate card entry covering `dateStr`.
 *
 * Admin-only: this is what the admin calendar prints in each day cell (the
 * configured rate, and what each plan's ratio makes of it). No guest-facing
 * price is derived on the client any more — with promotions, what a stay
 * costs depends on which nights it overlaps, on a minimum stay, and on
 * comparing competing offers in CHF, and a quote has to be the same number
 * that will actually be charged. The booking widget asks the server
 * instead (see getStayQuote / getFromPrice in lib/api.ts).
 */
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

// Whether `dateStr` is covered by any configured rate — i.e. whether it is
// bookable at all. Availability, not pricing, which is why this stays on the
// client: it decides which days the calendar disables.
export function hasRateFor(prices: PriceLike[], dateStr: string): boolean {
  return prices.some((price) =>
    price.period.date_ranges.some(
      (range) => dateStr >= range.begin_date && dateStr <= range.end_date
    )
  );
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

// The promotions covering `dateStr`, for the calendar's highlight + tooltip.
// begin_date/end_date are both inclusive, matching the backend's own rule
// that a night N is discounted when begin_date <= N <= end_date.
export function promotionsForDate<T extends { begin_date: string; end_date: string }>(
  promotions: T[],
  dateStr: string
): T[] {
  return promotions.filter((p) => dateStr >= p.begin_date && dateStr <= p.end_date);
}
