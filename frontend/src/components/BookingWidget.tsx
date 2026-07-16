"use client";

import { useState, useRef, useEffect, useLayoutEffect } from "react";
import { DayPicker } from "react-day-picker";
import type { DateRange } from "react-day-picker";
import { format, differenceInCalendarDays, parse, isValid, isBefore, isAfter, isSameDay } from "date-fns";
import { enUS, de, fr, it } from "date-fns/locale";
import type { Locale as DateFnsLocale } from "date-fns";
import "react-day-picker/style.css";
import type { Locale } from "@/lib/i18n-config";
import { useCurrency } from "@/lib/currency-context";
import { formatPrice } from "@/lib/currency-config";
import { listPublicPlans, listPublicPrices, type Plan, type Price } from "@/lib/api";
import { findDailyRate, FALLBACK_DAILY_RATE } from "@/lib/pricing";
import BookingModal, { type BookingModalDict } from "@/components/BookingModal";

const CLEANING_FEE = 50;
const CHILD_AGES = Array.from({ length: 18 }, (_, i) => i);
const DISPLAY_FORMAT = "dd/MM/yyyy";

const DATE_FNS_LOCALES: Record<Locale, DateFnsLocale> = { en: enUS, de, fr, it };

type Child = { age: number | null };

export interface BookingDict {
  planYourStay: string;
  perNight: string;
  night: string;
  nights: string;
  guest: string;
  guests: string;
  selectDates: string;
  checkIn: string;
  checkOut: string;
  openCalendar: string;
  guestsSection: string;
  adults: string;
  adultsAge: string;
  children: string;
  childrenAge: string;
  childrenAges: string;
  child: string;
  selectAge: string;
  underOne: string;
  yr: string;
  yrs: string;
  cleaningFee: string;
  total: string;
  bookNow: string;
  noCharge: string;
  modal: BookingModalDict;
}

function tryParseDate(str: string): Date | null {
  const fmts = ["dd/MM/yyyy", "d/M/yyyy", "dd-MM-yyyy", "d-M-yyyy", "dd MMM yyyy", "d MMM yyyy"];
  for (const fmt of fmts) {
    const d = parse(str.trim(), fmt, new Date());
    if (isValid(d) && d.getFullYear() >= new Date().getFullYear()) return d;
  }
  return null;
}

export default function BookingWidget({ dict, lang }: { dict: BookingDict; lang: Locale }) {
  const today = new Date();
  const dateFnsLocale = DATE_FNS_LOCALES[lang];
  const { currency } = useCurrency();
  const [range, setRange] = useState<DateRange | undefined>();
  const [hoverDate, setHoverDate] = useState<Date | undefined>(undefined);
  const [checkInText, setCheckInText] = useState("");
  const [checkOutText, setCheckOutText] = useState("");
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [adults, setAdults] = useState(2);
  const [children, setChildren] = useState<Child[]>([]);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [prices, setPrices] = useState<Price[]>([]);
  const [bookingModalOpen, setBookingModalOpen] = useState(false);
  const [calendarAnchor, setCalendarAnchor] = useState<{ top: number; right: number } | null>(null);
  const dateRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listPublicPlans()
      .then((plans) => setPlan(plans[0] ?? null))
      .catch(() => setPlan(null));
    listPublicPrices()
      .then(setPrices)
      .catch(() => setPrices([]));
  }, []);

  // Close calendar on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dateRef.current && !dateRef.current.contains(e.target as Node)) {
        setCalendarOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Pin the dropdown's top-right corner to the date row's on-screen position — it then
  // grows left/down as it needs, without pushing the rest of the card (and getting
  // clipped by the page's fixed-viewport, non-scrolling hero) out of view.
  useLayoutEffect(() => {
    if (!calendarOpen) return;
    const updateAnchor = () => {
      if (!dateRef.current) return;
      const rect = dateRef.current.getBoundingClientRect();
      setCalendarAnchor({ top: rect.bottom + 8, right: window.innerWidth - rect.right });
    };
    updateAnchor();
    window.addEventListener("resize", updateAnchor);
    return () => window.removeEventListener("resize", updateAnchor);
  }, [calendarOpen]);

  // Sync text inputs whenever the calendar range changes
  useEffect(() => {
    setCheckInText(range?.from ? format(range.from, DISPLAY_FORMAT) : "");
    setCheckOutText(range?.to ? format(range.to, DISPLAY_FORMAT) : "");
    // Auto-close once both dates are chosen
    if (range?.from && range?.to) setCalendarOpen(false);
  }, [range]);

  const handleCheckInChange = (value: string) => {
    setCheckInText(value);
    const parsed = tryParseDate(value);
    if (parsed) {
      setRange({ from: parsed, to: undefined });
    }
  };

  const handleCheckOutChange = (value: string) => {
    setCheckOutText(value);
    const parsed = tryParseDate(value);
    if (parsed && range?.from && !isBefore(parsed, range.from)) {
      setRange({ from: range.from, to: parsed });
    }
  };

  const nights =
    range?.from && range?.to ? differenceInCalendarDays(range.to, range.from) : 0;
  const totalGuests = adults + children.length;
  const matchedRate = findDailyRate(prices, format(range?.from ?? today, "yyyy-MM-dd"));
  const pricePerNight = (matchedRate?.dailyRate ?? FALLBACK_DAILY_RATE) * (plan?.price_ratio ?? 1);
  const total = nights * pricePerNight;
  const isFormValid =
    !!range?.from &&
    !!range?.to &&
    nights > 0 &&
    children.every((child) => child.age !== null);

  const handleBookNow = () => {
    if (!isFormValid) return;
    setBookingModalOpen(true);
  };

  const addChild = () => {
    if (children.length < 4) setChildren([...children, { age: null }]);
  };
  const removeChild = () => {
    if (children.length > 0) setChildren(children.slice(0, -1));
  };
  const updateChildAge = (index: number, age: number | null) => {
    const updated = [...children];
    updated[index].age = age;
    setChildren(updated);
  };

  return (
    <div className="bg-white rounded-2xl shadow-2xl w-full">
      {/* ── Header ────────────────────────────────────────── */}
      <div
        className="px-6 py-5 rounded-t-2xl"
        style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
      >
        <div className="flex items-baseline justify-between">
          <h2 className="text-xl font-bold text-white">{dict.planYourStay}</h2>
          <div className="text-right">
            <span className="text-2xl font-bold text-white">{formatPrice(pricePerNight, currency)}</span>
            <span className="text-teal-200 text-sm ml-1">{dict.perNight}</span>
          </div>
        </div>
        {nights > 0 && (
          <p className="text-teal-100 text-sm mt-1">
            {nights} {nights !== 1 ? dict.nights : dict.night} · {totalGuests}{" "}
            {totalGuests !== 1 ? dict.guests : dict.guest}
          </p>
        )}
      </div>

      <div className="p-6">
        {/* ── Date inputs + dropdown calendar ───────────────── */}
        <section ref={dateRef} className="relative mb-5">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">
            {dict.selectDates}
          </h3>

          <div className="flex items-end gap-2">
            <DateField
              label={dict.checkIn}
              value={checkInText}
              onChange={handleCheckInChange}
              onCalendarClick={() => setCalendarOpen((v) => !v)}
              active={calendarOpen}
              filled={!!range?.from}
              openCalendarLabel={dict.openCalendar}
            />
            <span className="pb-[11px] text-gray-300 text-lg select-none">→</span>
            <DateField
              label={dict.checkOut}
              value={checkOutText}
              onChange={handleCheckOutChange}
              onCalendarClick={() => setCalendarOpen((v) => !v)}
              active={calendarOpen}
              filled={!!range?.to}
              openCalendarLabel={dict.openCalendar}
            />
          </div>

          {/* Dropdown calendar — pinned to the date row's top-right corner and fixed to the
              viewport, so it grows left/down to fit the cozy layout without ever scrolling
              or being clipped by the page's non-scrolling hero section. */}
          {calendarOpen && calendarAnchor && (
            <div
              className="fixed z-40 flex justify-center bg-white rounded-2xl shadow-2xl border border-gray-200 p-5 w-max max-w-[calc(100vw-1.5rem)] overflow-x-auto"
              style={{ top: calendarAnchor.top, right: calendarAnchor.right }}
            >
              <DayPicker
                mode="range"
                navLayout="around"
                style={{
                  "--rdp-months-gap": "1.5rem",
                } as React.CSSProperties}
                styles={{ months: { flexWrap: "nowrap" } }}
                selected={range}
                defaultMonth={range?.from ?? today}
                onSelect={setRange}
                onDayClick={(date, modifiers) => {
                  if (modifiers.disabled) return;
                  // Both dates were already picked; start a fresh selection instead of adjusting the old range
                  if (range?.from && range?.to) {
                    setRange({ from: date, to: undefined });
                  }
                }}
                numberOfMonths={2}
                disabled={{ before: today }}
                showOutsideDays={false}
                locale={dateFnsLocale}
                min={1}
                onDayMouseEnter={(date) => setHoverDate(date)}
                onDayMouseLeave={() => setHoverDate(undefined)}
                modifiers={{
                  hoverRange: (date) =>
                    !!range?.from &&
                    !range?.to &&
                    !!hoverDate &&
                    isAfter(hoverDate, range.from) &&
                    isAfter(date, range.from) &&
                    isBefore(date, hoverDate),
                  hoverRangeEnd: (date) =>
                    !!range?.from &&
                    !range?.to &&
                    !!hoverDate &&
                    isAfter(hoverDate, range.from) &&
                    isSameDay(date, hoverDate),
                }}
                modifiersClassNames={{
                  hoverRange: "rdp-range_middle",
                  hoverRangeEnd: "rdp-range_end",
                }}
              />
            </div>
          )}
        </section>

        <div className="border-t border-gray-100 my-4" />

        {/* ── Guests ────────────────────────────────────────── */}
        <section className="mb-5">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">
            {dict.guestsSection}
          </h3>

          <div className="flex items-center justify-between py-3 border-b border-gray-100">
            <div>
              <p className="font-medium text-gray-800 text-sm">{dict.adults}</p>
              <p className="text-xs text-gray-400">{dict.adultsAge}</p>
            </div>
            <Counter
              value={adults}
              min={1}
              max={5}
              onDecrement={() => setAdults(adults - 1)}
              onIncrement={() => setAdults(adults + 1)}
            />
          </div>

          <div className="flex items-center justify-between py-3">
            <div>
              <p className="font-medium text-gray-800 text-sm">{dict.children}</p>
              <p className="text-xs text-gray-400">{dict.childrenAge}</p>
            </div>
            <Counter
              value={children.length}
              min={0}
              max={4}
              onDecrement={removeChild}
              onIncrement={addChild}
            />
          </div>

          {children.length > 0 && (
            <div className="mt-3 p-3 bg-amber-50 rounded-xl border border-amber-100">
              <p className="text-xs font-semibold text-amber-700 uppercase tracking-wider mb-3">
                {dict.childrenAges}
              </p>
              <div className="flex flex-wrap gap-3">
                {children.map((child, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className="text-xs text-gray-500 whitespace-nowrap">
                      {dict.child} {i + 1}
                    </span>
                    <select
                      value={child.age ?? ""}
                      required
                      onChange={(e) =>
                        updateChildAge(i, e.target.value === "" ? null : Number(e.target.value))
                      }
                      className={`text-sm border rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-teal-300 cursor-pointer ${
                        child.age === null
                          ? "border-red-300 text-gray-400 focus:border-red-400"
                          : "border-amber-200 text-gray-700 focus:border-teal-500"
                      }`}
                    >
                      <option value="" disabled>{dict.selectAge}</option>
                      {CHILD_AGES.map((age) => (
                        <option key={age} value={age}>
                          {age === 0 ? dict.underOne : `${age} ${age !== 1 ? dict.yrs : dict.yr}`}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* ── Price summary ─────────────────────────────────── */}
        {nights > 0 && (
          <div className="bg-gray-50 rounded-xl p-4 mb-5 border border-gray-200 text-sm">
            <div className="flex justify-between text-gray-600 mb-1">
              <span>{formatPrice(pricePerNight, currency)} × {nights} {nights !== 1 ? dict.nights : dict.night}</span>
              <span>{formatPrice(total, currency)}</span>
            </div>
            <div className="flex justify-between text-gray-600 mb-1">
              <span>{dict.cleaningFee}</span>
              <span>{formatPrice(CLEANING_FEE, currency)}</span>
            </div>
            <div className="border-t border-gray-200 mt-2 pt-2 flex justify-between font-semibold text-gray-900">
              <span>{dict.total}</span>
              <span>{formatPrice(total + CLEANING_FEE, currency)}</span>
            </div>
          </div>
        )}

        {/* ── Book Now ──────────────────────────────────────── */}
        <button
          className={`w-full text-white font-semibold py-4 rounded-xl text-base transition-all shadow-lg ${
            isFormValid
              ? "active:scale-[0.98] cursor-pointer"
              : "opacity-50 cursor-not-allowed"
          }`}
          style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
          onClick={handleBookNow}
          disabled={!isFormValid}
        >
          {dict.bookNow}
        </button>

        <p className="text-center text-xs text-gray-400 mt-3">
          {dict.noCharge}
        </p>
      </div>

      {bookingModalOpen && range?.from && range?.to && (
        <BookingModal
          dict={dict.modal}
          checkIn={range.from}
          checkOut={range.to}
          nights={nights}
          onClose={() => setBookingModalOpen(false)}
        />
      )}
    </div>
  );
}

/* ── DateField ─────────────────────────────────────────── */
function DateField({
  label,
  value,
  onChange,
  onCalendarClick,
  active,
  filled,
  openCalendarLabel,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  onCalendarClick: () => void;
  active: boolean;
  filled: boolean;
  openCalendarLabel: string;
}) {
  return (
    <div className="flex-1 min-w-0">
      <label className="block text-xs font-medium text-gray-400 mb-1">{label}</label>
      <div className="relative">
        <input
          type="text"
          value={value}
          placeholder="DD/MM/YYYY"
          onChange={(e) => onChange(e.target.value)}
          className={`w-full pl-3 pr-9 py-2.5 rounded-xl border text-sm transition-colors focus:outline-none focus:ring-1 ${
            filled
              ? "border-teal-400 bg-teal-50 text-gray-800 focus:border-teal-500 focus:ring-teal-200"
              : active
              ? "border-teal-400 bg-white text-gray-800 focus:border-teal-500 focus:ring-teal-200"
              : "border-gray-200 bg-gray-50 text-gray-800 focus:border-teal-400 focus:ring-teal-100"
          } placeholder-gray-300`}
        />
        <button
          type="button"
          onClick={onCalendarClick}
          className={`absolute right-2.5 top-1/2 -translate-y-1/2 transition-colors cursor-pointer ${
            active ? "text-teal-600" : "text-gray-400 hover:text-teal-600"
          }`}
          aria-label={openCalendarLabel}
        >
          <CalendarIcon />
        </button>
      </div>
    </div>
  );
}

/* ── CalendarIcon ──────────────────────────────────────── */
function CalendarIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <rect x="1" y="3" width="14" height="12" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M1 7h14" stroke="currentColor" strokeWidth="1.5" />
      <path d="M5 1v4M11 1v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

/* ── Counter ───────────────────────────────────────────── */
function Counter({
  value,
  min,
  max,
  onDecrement,
  onIncrement,
}: {
  value: number;
  min: number;
  max: number;
  onDecrement: () => void;
  onIncrement: () => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <button
        onClick={onDecrement}
        disabled={value <= min}
        className="w-8 h-8 rounded-full border-2 border-gray-300 flex items-center justify-center text-gray-600 font-medium hover:border-teal-500 hover:text-teal-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
      >
        −
      </button>
      <span className="w-5 text-center font-semibold text-gray-800 text-sm">{value}</span>
      <button
        onClick={onIncrement}
        disabled={value >= max}
        className="w-8 h-8 rounded-full border-2 border-gray-300 flex items-center justify-center text-gray-600 font-medium hover:border-teal-500 hover:text-teal-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
      >
        +
      </button>
    </div>
  );
}
