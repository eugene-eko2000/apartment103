"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { format, parse } from "date-fns";
import {
  ApiError,
  listBookings,
  listClosures,
  listPlans,
  listPrices,
  type Booking,
  type Closure,
  type Plan,
  type Price,
} from "@/lib/api";
import { findDailyRate, findMinStay, type MatchedRate } from "@/lib/pricing";
import { useAdminAuth } from "@/lib/admin-auth";

const ISO_FORMAT = "yyyy-MM-dd";
const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function parseISODate(value: string): Date | undefined {
  const parsed = parse(value, ISO_FORMAT, new Date());
  return Number.isNaN(parsed.getTime()) ? undefined : parsed;
}

function diffDays(a: Date, b: Date): number {
  return Math.round((b.getTime() - a.getTime()) / 86_400_000);
}

function isSameDate(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

// Chosen to stay legible with the white guest-name text on booking bars.
const BOOKING_COLOR = "#4f46e5";
// Neutral gray so a platform closure reads as distinct from an actual booking.
const CLOSURE_COLOR = "#6b7280";

interface BookingSegment {
  booking: Booking;
  label: string;
  guestName: string;
  priceLabel: string;
  from: Date;
  to: Date;
  checkout: Date;
}

interface ClosureSegment {
  closure: Closure;
  label: string;
  from: Date;
  to: Date;
  checkout: Date;
}

interface WeekGeometry {
  coveredStartCol: number;
  coveredEndCol: number;
  barStartCol: number;
  barEndCol: number;
  startsThisWeek: boolean;
  endsThisWeek: boolean;
}

// Shared bar/coverage geometry for a single week row: which day columns the
// segment occupies (coveredStartCol/coveredEndCol), and where its bar should
// be drawn (barStartCol/barEndCol), rounding the bar's ends only where the
// check-in/checkout day actually falls in this row rather than a
// continuation from/to another week.
function computeWeekGeometry<T extends { from: Date; to: Date; checkout: Date }>(
  segment: T,
  weekStart: Date,
  weekEnd: Date
): T & WeekGeometry {
  const nightsInWeek = segment.to >= weekStart && segment.from <= weekEnd;
  const coveredStartCol = nightsInWeek ? Math.max(0, diffDays(weekStart, segment.from)) : 7;
  const coveredEndCol = nightsInWeek ? Math.min(6, diffDays(weekStart, segment.to)) : -1;

  const rawFrom = diffDays(weekStart, segment.from);
  const rawCheckout = diffDays(weekStart, segment.checkout);
  const startsThisWeek = rawFrom >= 0;
  const endsThisWeek = rawCheckout <= 6;
  const barStartCol = Math.max(0, rawFrom) + (startsThisWeek ? 0.25 : 0);
  const barEndCol = Math.min(6, rawCheckout) + (endsThisWeek ? 0.23 : 1);

  return { ...segment, coveredStartCol, coveredEndCol, barStartCol, barEndCol, startsThisWeek, endsThisWeek };
}

interface DayCell {
  date: Date;
  inMonth: boolean;
}

function ChevronDownIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5 shrink-0" aria-hidden="true">
      <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PriceDropdown({ rate, plans }: { rate: MatchedRate; plans: Plan[] }) {
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<{ top: number; left: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const openDropdown = () => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setAnchor({ top: rect.bottom + window.scrollY + 4, left: rect.left + window.scrollX });
    setOpen(true);
  };

  useEffect(() => {
    if (!open) return;
    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target) || dropdownRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        ref={triggerRef}
        onClick={(e) => {
          e.stopPropagation();
          if (open) setOpen(false);
          else openDropdown();
        }}
        className="flex items-center gap-0.5 text-sm font-medium text-slate-700 dark:text-slate-200 hover:text-indigo-600 dark:hover:text-indigo-400 cursor-pointer"
      >
        {rate.currency} {Math.round(rate.dailyRate)}
        <ChevronDownIcon />
      </button>

      {open &&
        anchor &&
        createPortal(
          <div
            ref={dropdownRef}
            className="absolute z-[120] min-w-[200px] bg-white dark:bg-slate-800 rounded-lg shadow-2xl border border-slate-200 dark:border-slate-700 py-1"
            style={{ top: anchor.top, left: anchor.left }}
          >
            {plans.length === 0 ? (
              <p className="px-3 py-2 text-xs text-slate-400 dark:text-slate-500">No plans configured.</p>
            ) : (
              plans.map((plan) => (
                <div key={plan._id} className="flex items-center justify-between gap-4 px-3 py-1.5 text-sm">
                  <span className="text-slate-600 dark:text-slate-300">{plan.name}</span>
                  <span className="font-medium text-slate-800 dark:text-slate-100">
                    {rate.currency} {Math.round(rate.dailyRate * plan.price_ratio)}
                  </span>
                </div>
              ))
            )}
          </div>,
          document.body
        )}
    </>
  );
}

export default function CalendarPanel() {
  const { session, logout } = useAdminAuth();
  const token = session!.token;

  const today = useMemo(() => new Date(), []);
  const [month, setMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [closures, setClosures] = useState<Closure[]>([]);
  const [prices, setPrices] = useState<Price[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listBookings(token), listClosures(token), listPrices(token), listPlans(token)])
      .then(([bookingList, closureList, priceList, planList]) => {
        setBookings(bookingList);
        setClosures(closureList);
        setPrices(priceList);
        setPlans(planList);
        setError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) return logout();
        setError(err instanceof ApiError ? err.message : String(err));
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const segments = useMemo<BookingSegment[]>(
    () =>
      bookings
        .filter((booking) => booking.status !== "Cancelled")
        .flatMap((booking) =>
          booking.date_ranges
            .map((range) => {
              const from = parseISODate(range.begin_date);
              const checkout = parseISODate(range.end_date);
              if (!from || !checkout) return null;
              // end_date is the checkout day, which is bookable by the next guest,
              // so the displayed bar should stop at the last occupied night.
              const to = new Date(checkout);
              to.setDate(to.getDate() - 1);
              const guestName = `${booking.guest.first_name} ${booking.guest.family_name}`;
              const priceLabel = `${booking.currency} ${Math.round(range.price)}`;
              return {
                booking,
                label: `${guestName} · ${priceLabel}`,
                guestName,
                priceLabel,
                from,
                to,
                checkout,
              };
            })
            .filter((s): s is BookingSegment => s !== null)
        ),
    [bookings]
  );

  const closureSegments = useMemo<ClosureSegment[]>(
    () =>
      closures
        .map((closure) => {
          const from = parseISODate(closure.begin_date);
          const checkout = parseISODate(closure.end_date);
          if (!from || !checkout) return null;
          // Same end-exclusive convention as booking date ranges: end_date
          // is the day the closure lifts, so the bar stops the day before.
          const to = new Date(checkout);
          to.setDate(to.getDate() - 1);
          return { closure, label: closure.platform, from, to, checkout };
        })
        .filter((s): s is ClosureSegment => s !== null),
    [closures]
  );

  const weeks = useMemo<DayCell[][]>(() => {
    const year = month.getFullYear();
    const monthIdx = month.getMonth();
    const daysInMonth = new Date(year, monthIdx + 1, 0).getDate();
    const firstWeekDay = (new Date(year, monthIdx, 1).getDay() + 6) % 7; // Monday = 0
    const totalWeeks = Math.ceil((firstWeekDay + daysInMonth) / 7);

    return Array.from({ length: totalWeeks }, (_, w) =>
      Array.from({ length: 7 }, (_, c) => {
        const dayNum = w * 7 + c - firstWeekDay + 1;
        return { date: new Date(year, monthIdx, dayNum), inMonth: dayNum >= 1 && dayNum <= daysInMonth };
      })
    );
  }, [month]);

  if (loading) return <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>;
  if (error) return <p className="text-sm text-red-600 dark:text-red-400">{error}</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100">{format(month, "MMMM yyyy")}</h2>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={() => setMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1))}
            className="w-8 h-8 flex items-center justify-center rounded-lg border border-slate-300 dark:border-slate-600 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 cursor-pointer"
            aria-label="Previous month"
          >
            ‹
          </button>
          <button
            type="button"
            onClick={() => setMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1))}
            className="w-8 h-8 flex items-center justify-center rounded-lg border border-slate-300 dark:border-slate-600 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 cursor-pointer"
            aria-label="Next month"
          >
            ›
          </button>
        </div>
      </div>

      <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
        <div className="grid grid-cols-7 border-b border-slate-200 dark:border-slate-700">
          {WEEKDAY_LABELS.map((label) => (
            <div
              key={label}
              className="py-2 text-center text-xs font-semibold text-slate-500 dark:text-slate-400 border-l border-slate-200 dark:border-slate-700 first:border-l-0"
            >
              {label}
            </div>
          ))}
        </div>

        {weeks.map((week, weekIdx) => {
          const weekStart = week[0].date;
          const weekEnd = week[6].date;
          const weekSegments = segments
            .filter((s) => s.checkout >= weekStart && s.from <= weekEnd)
            .map((s) => computeWeekGeometry(s, weekStart, weekEnd));

          const weekClosureSegments = closureSegments
            .filter((s) => s.checkout >= weekStart && s.from <= weekEnd)
            .map((s) => computeWeekGeometry(s, weekStart, weekEnd));

          return (
            <div
              key={weekIdx}
              className="relative grid grid-cols-7 border-t border-slate-200 dark:border-slate-700 first:border-t-0"
            >
              {week.map((cell, colIdx) => {
                const dateStr = format(cell.date, ISO_FORMAT);
                const covered =
                  weekSegments.some((s) => colIdx >= s.coveredStartCol && colIdx <= s.coveredEndCol) ||
                  weekClosureSegments.some((s) => colIdx >= s.coveredStartCol && colIdx <= s.coveredEndCol);
                const rate = cell.inMonth && !covered ? findDailyRate(prices, dateStr) : null;
                const minStay = rate ? findMinStay(prices, dateStr) : null;
                const isToday = cell.inMonth && isSameDate(cell.date, today);
                const isUnavailable = cell.inMonth && !covered && !rate;

                return (
                  <div
                    key={colIdx}
                    className={`min-h-[112px] p-2 border-l border-slate-200 dark:border-slate-700 first:border-l-0 ${
                      isToday
                        ? "ring-2 ring-inset ring-indigo-500 shadow-[inset_0_0_14px_2px_rgba(99,102,241,0.45)]"
                        : ""
                    } ${
                      isUnavailable
                        ? "bg-[repeating-linear-gradient(45deg,rgba(148,163,184,0.3)_0,rgba(148,163,184,0.3)_1px,transparent_1px,transparent_8px)] dark:bg-[repeating-linear-gradient(45deg,rgba(100,116,139,0.35)_0,rgba(100,116,139,0.35)_1px,transparent_1px,transparent_8px)]"
                        : ""
                    }`}
                  >
                    {cell.inMonth && (
                      <>
                        <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                          {cell.date.getDate()}
                        </span>
                        {!covered && rate && (
                          <div className="mt-5 flex flex-col items-center gap-1 text-center">
                            <span className="text-sm text-slate-400 dark:text-slate-500">Available</span>
                            <PriceDropdown rate={rate} plans={plans} />
                            {minStay !== null && (
                              <span className="text-xs text-slate-400 dark:text-slate-500">
                                Min {minStay} {minStay === 1 ? "night" : "nights"}
                              </span>
                            )}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                );
              })}

              {weekSegments.map((s) => (
                <div
                  key={`${s.booking._id}-${weekIdx}`}
                  title={`${s.label} (${format(s.from, ISO_FORMAT)} – ${format(s.checkout, ISO_FORMAT)})`}
                  className={`absolute top-8 h-7 flex items-center gap-1.5 px-3 text-xs font-medium text-white truncate ${
                    s.startsThisWeek ? "rounded-l-full" : ""
                  } ${s.endsThisWeek ? "rounded-r-full" : ""}`}
                  style={{
                    left: `calc(${(s.barStartCol / 7) * 100}% + 4px)`,
                    width: `calc(${((s.barEndCol - s.barStartCol) / 7) * 100}% - 8px)`,
                    backgroundColor: BOOKING_COLOR,
                  }}
                >
                  <span className="truncate">{s.guestName}</span>
                  <span className="opacity-80 shrink-0">{s.priceLabel}</span>
                </div>
              ))}

              {weekClosureSegments.map((s) => (
                <div
                  key={`${s.closure._id}-${weekIdx}`}
                  title={`${s.label} (${format(s.from, ISO_FORMAT)} – ${format(s.checkout, ISO_FORMAT)})`}
                  className={`absolute top-8 h-7 flex items-center px-3 text-xs font-medium text-white truncate ${
                    s.startsThisWeek ? "rounded-l-full" : ""
                  } ${s.endsThisWeek ? "rounded-r-full" : ""}`}
                  style={{
                    left: `calc(${(s.barStartCol / 7) * 100}% + 4px)`,
                    width: `calc(${((s.barEndCol - s.barStartCol) / 7) * 100}% - 8px)`,
                    backgroundColor: CLOSURE_COLOR,
                  }}
                >
                  <span className="truncate">{s.label}</span>
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
