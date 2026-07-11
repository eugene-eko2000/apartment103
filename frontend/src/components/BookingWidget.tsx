"use client";

import { useState, useRef, useEffect } from "react";
import { DayPicker } from "react-day-picker";
import type { DateRange } from "react-day-picker";
import { format, differenceInCalendarDays, parse, isValid, isBefore } from "date-fns";
import "react-day-picker/style.css";

const PRICE_PER_NIGHT = 150;
const CHILD_AGES = Array.from({ length: 18 }, (_, i) => i);
const DISPLAY_FORMAT = "dd/MM/yyyy";

type Child = { age: number | null };

function tryParseDate(str: string): Date | null {
  const fmts = ["dd/MM/yyyy", "d/M/yyyy", "dd-MM-yyyy", "d-M-yyyy", "dd MMM yyyy", "d MMM yyyy"];
  for (const fmt of fmts) {
    const d = parse(str.trim(), fmt, new Date());
    if (isValid(d) && d.getFullYear() >= new Date().getFullYear()) return d;
  }
  return null;
}

export default function BookingWidget() {
  const today = new Date();
  const [range, setRange] = useState<DateRange | undefined>();
  const [checkInText, setCheckInText] = useState("");
  const [checkOutText, setCheckOutText] = useState("");
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [adults, setAdults] = useState(2);
  const [children, setChildren] = useState<Child[]>([]);
  const dateRef = useRef<HTMLDivElement>(null);

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
  const total = nights * PRICE_PER_NIGHT;

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
          <h2 className="text-xl font-bold text-white">Plan Your Stay</h2>
          <div className="text-right">
            <span className="text-2xl font-bold text-white">€{PRICE_PER_NIGHT}</span>
            <span className="text-teal-200 text-sm ml-1">/ night</span>
          </div>
        </div>
        {nights > 0 && (
          <p className="text-teal-100 text-sm mt-1">
            {nights} night{nights !== 1 ? "s" : ""} · {totalGuests} guest
            {totalGuests !== 1 ? "s" : ""}
          </p>
        )}
      </div>

      <div className="p-6">
        {/* ── Date inputs + dropdown calendar ───────────────── */}
        <section ref={dateRef} className="relative mb-5">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">
            Select dates
          </h3>

          <div className="flex items-end gap-2">
            <DateField
              label="Check-in"
              value={checkInText}
              onChange={handleCheckInChange}
              onCalendarClick={() => setCalendarOpen((v) => !v)}
              active={calendarOpen}
              filled={!!range?.from}
            />
            <span className="pb-[11px] text-gray-300 text-lg select-none">→</span>
            <DateField
              label="Check-out"
              value={checkOutText}
              onChange={handleCheckOutChange}
              onCalendarClick={() => setCalendarOpen((v) => !v)}
              active={calendarOpen}
              filled={!!range?.to}
            />
          </div>

          {/* Dropdown calendar */}
          {calendarOpen && (
            <div className="absolute top-full left-0 mt-2 z-50 bg-white rounded-2xl shadow-2xl border border-gray-200 p-4">
              <DayPicker
                mode="range"
                selected={range}
                onSelect={setRange}
                numberOfMonths={2}
                disabled={{ before: today }}
                showOutsideDays={false}
              />
            </div>
          )}
        </section>

        <div className="border-t border-gray-100 my-4" />

        {/* ── Guests ────────────────────────────────────────── */}
        <section className="mb-5">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">
            Guests
          </h3>

          <div className="flex items-center justify-between py-3 border-b border-gray-100">
            <div>
              <p className="font-medium text-gray-800 text-sm">Adults</p>
              <p className="text-xs text-gray-400">Age 18+</p>
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
              <p className="font-medium text-gray-800 text-sm">Children</p>
              <p className="text-xs text-gray-400">Ages 0–17</p>
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
                Children&rsquo;s ages
              </p>
              <div className="flex flex-wrap gap-3">
                {children.map((child, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className="text-xs text-gray-500 whitespace-nowrap">
                      Child {i + 1}
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
                      <option value="" disabled>Select age</option>
                      {CHILD_AGES.map((age) => (
                        <option key={age} value={age}>
                          {age === 0 ? "Under 1" : `${age} yr${age !== 1 ? "s" : ""}`}
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
              <span>€{PRICE_PER_NIGHT} × {nights} night{nights !== 1 ? "s" : ""}</span>
              <span>€{total}</span>
            </div>
            <div className="flex justify-between text-gray-600 mb-1">
              <span>Cleaning fee</span>
              <span>€50</span>
            </div>
            <div className="border-t border-gray-200 mt-2 pt-2 flex justify-between font-semibold text-gray-900">
              <span>Total</span>
              <span>€{total + 50}</span>
            </div>
          </div>
        )}

        {/* ── Book Now ──────────────────────────────────────── */}
        <button
          className="w-full text-white font-semibold py-4 rounded-xl text-base transition-all shadow-lg active:scale-[0.98] cursor-pointer"
          style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
          onClick={() => alert("Booking flow — coming soon!")}
        >
          Book Now
        </button>

        <p className="text-center text-xs text-gray-400 mt-3">
          No charge yet — you&apos;ll review before confirming
        </p>
      </div>
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
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  onCalendarClick: () => void;
  active: boolean;
  filled: boolean;
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
          aria-label="Open calendar"
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
