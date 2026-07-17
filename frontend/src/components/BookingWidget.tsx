"use client";

import { useState, useRef, useId, useEffect, useLayoutEffect } from "react";
import { DayPicker } from "react-day-picker";
import type { DateRange } from "react-day-picker";
import { format, differenceInCalendarDays, parse, isValid, isBefore, isAfter, isSameDay } from "date-fns";
import { enUS, de, fr, it } from "date-fns/locale";
import type { Locale as DateFnsLocale } from "date-fns";
import "react-day-picker/style.css";
import type { Locale } from "@/lib/i18n-config";
import { useCurrency } from "@/lib/currency-context";
import { formatPrice } from "@/lib/currency-config";
import {
  ApiError,
  createBooking,
  createGuest,
  getGuest,
  listPublicPlans,
  listPublicPrices,
  registerGuestSelf,
  updateGuest,
  verifyToken,
  type Currency,
  type GuestInput,
  type Language,
  type Plan,
  type Price,
} from "@/lib/api";
import { findDailyRate, FALLBACK_CURRENCY, FALLBACK_DAILY_RATE } from "@/lib/pricing";
import BookingModal, { guestToForm, type BookingModalDict, type VerifiedIdentity } from "@/components/BookingModal";
import { clearGuestSession, readGuestSession, saveGuestSession } from "@/lib/guest-auth";

const CHILD_AGES = Array.from({ length: 18 }, (_, i) => i);
const DISPLAY_FORMAT = "dd/MM/yyyy";
const LANGUAGES: Language[] = ["en", "de", "fr", "it"];
const CURRENCIES: Currency[] = ["EUR", "CHF", "USD", "GBP"];

const DATE_FNS_LOCALES: Record<Locale, DateFnsLocale> = { en: enUS, de, fr, it };
const TRANSITION_MS = 380;

type Child = { age: number | null };
type GuestFlowStep = "form" | "submitting" | "success" | "error";

export interface BookingDict {
  planYourStay: string;
  fromPrefix: string;
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
  bookNow: string;
  cancel: string;
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
  const [identityModalOpen, setIdentityModalOpen] = useState(false);
  const [calendarAnchor, setCalendarAnchor] = useState<{ top: number; right: number } | null>(null);
  const dateRef = useRef<HTMLDivElement>(null);
  const widgetRef = useRef<HTMLDivElement>(null);
  // Rect captured live (via captureRect()) right before extended toggles, so
  // the FLIP effect below knows where to animate from.
  const prevRectRef = useRef<DOMRect | null>(null);

  // ── Post-OTP booking procedure ──────────────────────────
  const [verified, setVerified] = useState<VerifiedIdentity | null>(null);
  const [guestForm, setGuestForm] = useState<GuestInput | null>(null);
  const [guestStep, setGuestStep] = useState<GuestFlowStep>("form");
  const [guestName, setGuestName] = useState("");
  const [pending, setPending] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  // True while a stored guest session's bearer token is being validated
  // against the API in response to a Book click.
  const [checkingSession, setCheckingSession] = useState(false);
  // The widget's pinned top once settled into (or out of) extended mode — its
  // top edge never moves, only left/width/height animate.
  const [pinnedTop, setPinnedTop] = useState<number | null>(null);
  const extended = verified !== null;

  const captureRect = () => {
    if (widgetRef.current) prevRectRef.current = widgetRef.current.getBoundingClientRect();
  };

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

  // Animate the widget moving/resizing between its compact and extended
  // layouts (FLIP: freeze at the pre-toggle rect, then transition to the
  // natural post-toggle rect). The top edge is pinned to the same value in
  // both keyframes, so only left/width/height ever animate.
  useLayoutEffect(() => {
    const el = widgetRef.current;
    const fromRect = prevRectRef.current;
    prevRectRef.current = null;
    if (!el || !fromRect) return;

    const toRect = el.getBoundingClientRect();
    const top = fromRect.top;

    el.style.transition = "none";
    el.style.position = "fixed";
    el.style.top = `${top}px`;
    el.style.left = `${fromRect.left}px`;
    el.style.width = `${fromRect.width}px`;
    el.style.height = `${fromRect.height}px`;
    el.style.maxWidth = "none";
    el.style.maxHeight = "none";
    el.style.overflow = "hidden";
    el.style.zIndex = "91";
    // Tailwind v4's -translate-x-1/2 uses the standalone CSS `translate`
    // property, not `transform` — both must be cancelled so our absolute
    // `left` isn't shifted by a percentage of the (currently animating) width.
    el.style.transform = "none";
    el.style.translate = "none";
    // Force a layout flush so the browser commits the frozen start position
    // as its own frame before the next one animates away from it.
    void el.offsetHeight;

    const raf = requestAnimationFrame(() => {
      el.style.transition = ["left", "width", "height"]
        .map((prop) => `${prop} ${TRANSITION_MS}ms cubic-bezier(0.22, 1, 0.36, 1)`)
        .join(", ");
      el.style.left = `${toRect.left}px`;
      el.style.width = `${toRect.width}px`;
      el.style.height = `${toRect.height}px`;
    });

    const settle = () => {
      el.style.cssText = "";
      setPinnedTop(extended ? top : null);
    };
    el.addEventListener("transitionend", settle, { once: true });

    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener("transitionend", settle);
    };
  }, [extended]);

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
  const isFormValid =
    !!range?.from &&
    !!range?.to &&
    nights > 0 &&
    children.every((child) => child.age !== null);

  const handleBookClick = async () => {
    if (!isFormValid) return;
    const session = readGuestSession();
    console.log("BookingWidget: readGuestSession() returned", session);
    if (session) {
      setCheckingSession(true);
      try {
        // Confirm the stored bearer token is still accepted server-side
        // before resuming straight into the guest-details step with it.
        await verifyToken(session.token);
        const guest = await getGuest(session.guestId, session.token);
        handleVerified({
          authToken: session.token,
          expiresAt: session.expiresAt,
          guestId: guest._id,
          guestMode: "update",
          isAdminBooking: false,
          guestForm: guestToForm(guest),
        });
        return;
      } catch {
        // Token rejected or expired server-side — fall back to OTP below.
        clearGuestSession();
      } finally {
        setCheckingSession(false);
      }
    }
    setIdentityModalOpen(true);
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

  const handleVerified = (identity: VerifiedIdentity) => {
    captureRect();
    setVerified(identity);
    setGuestForm(identity.guestForm);
    setGuestStep("form");
    setFormError(null);
    setIdentityModalOpen(false);
    if (identity.guestMode === "update" && identity.guestId) {
      saveGuestSession({ token: identity.authToken, guestId: identity.guestId, expiresAt: identity.expiresAt });
    }
  };

  const resetBookingFlow = () => {
    captureRect();
    setVerified(null);
    setGuestForm(null);
    setGuestStep("form");
    setGuestName("");
    setFormError(null);
    setPending(false);
  };

  const handleDone = () => {
    resetBookingFlow();
    setRange(undefined);
    setAdults(2);
    setChildren([]);
  };

  const updateAddress = (field: keyof GuestInput["residence_address"], value: string) => {
    setGuestForm((prev) =>
      prev ? { ...prev, residence_address: { ...prev.residence_address, [field]: value } } : prev
    );
  };

  const submitBooking = async (finalGuestId: string, token: string) => {
    if (!plan || !range?.from || !range?.to) return;
    setGuestStep("submitting");
    try {
      const matchedRate = findDailyRate(prices, format(range.from, "yyyy-MM-dd"));
      const dailyRate = matchedRate?.dailyRate ?? FALLBACK_DAILY_RATE;
      const bookingCurrency: Currency = matchedRate?.currency ?? FALLBACK_CURRENCY;
      await createBooking(token, {
        guest_id: finalGuestId,
        cancellation_policy_id: plan.cancellation_policy.id,
        currency: bookingCurrency,
        date_ranges: [
          {
            begin_date: format(range.from, "yyyy-MM-dd"),
            end_date: format(range.to, "yyyy-MM-dd"),
            price: nights * dailyRate * plan.price_ratio,
          },
        ],
      });
      setGuestStep("success");
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : String(err));
      setGuestStep("error");
    }
  };

  const handleGuestFormSubmit = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!verified || !guestForm) return;
    setPending(true);
    setFormError(null);
    try {
      if (verified.guestMode === "create" && verified.isAdminBooking) {
        console.log("BookingWidget: creating guest via admin booking flow");
        const { guest, access_token, expires_in } = await createGuest(verified.authToken, guestForm);
        setGuestName(guest.first_name);
        saveGuestSession({
          token: access_token,
          guestId: guest._id,
          expiresAt: Date.now() + expires_in * 1000,
        });
        await submitBooking(guest._id, verified.authToken);
      } else if (verified.guestMode === "create") {
        console.log("BookingWidget: registering guest via self-service flow");
        const result = await registerGuestSelf(verified.authToken, guestForm);
        setGuestName(result.guest.first_name);
        saveGuestSession({
          token: result.access_token,
          guestId: result.guest._id,
          expiresAt: Date.now() + result.expires_in * 1000,
        });
        await submitBooking(result.guest._id, result.access_token);
      } else if (verified.guestMode === "update" && verified.guestId) {
        console.log("BookingWidget: updating guest via self-service flow");
        const guest = await updateGuest(verified.guestId, verified.authToken, guestForm);
        setGuestName(guest.first_name);
        await submitBooking(verified.guestId, verified.authToken);
      }
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : String(err));
      setGuestStep("error");
    } finally {
      setPending(false);
    }
  };

  const childAgesBlock = children.length > 0 && (
    <div className="p-3 bg-amber-50 rounded-xl border border-amber-100">
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
  );

  const dateAndGuestCalendar = calendarOpen && calendarAnchor && (
    <div
      className="fixed z-[95] flex justify-center bg-white rounded-2xl shadow-2xl border border-gray-200 p-5 w-max max-w-[calc(100vw-1.5rem)] overflow-x-auto"
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
  );

  return (
    <>
      <div
        className={`fixed inset-0 z-[90] bg-black/40 transition-opacity ease-in-out ${
          extended ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        }`}
        style={{ transitionDuration: `${TRANSITION_MS}ms` }}
      />
      <div
        ref={widgetRef}
        className={`bg-white rounded-2xl shadow-2xl w-full ${
          extended ? "fixed z-[91] left-1/2 -translate-x-1/2 max-w-3xl max-h-[90vh] overflow-y-auto" : ""
        }`}
        style={{ top: pinnedTop ?? undefined }}
      >
        {/* ── Header ────────────────────────────────────────── */}
        <div
          className="relative px-6 py-5 rounded-t-2xl"
          style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
        >
          <div className="flex items-baseline justify-between">
            <h2 className="text-xl font-bold text-white">{dict.planYourStay}</h2>
            <div className="text-right">
              <span className="text-teal-200 text-sm mr-1">{dict.fromPrefix}</span>
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
          {!extended ? (
            <>
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

                {dateAndGuestCalendar}
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

                {childAgesBlock && <div className="mt-3">{childAgesBlock}</div>}
              </section>

              {/* ── Book ──────────────────────────────────────────── */}
              <button
                className={`w-full text-white font-semibold py-4 rounded-xl text-base transition-all shadow-lg ${
                  isFormValid && !checkingSession
                    ? "active:scale-[0.98] cursor-pointer"
                    : "opacity-50 cursor-not-allowed"
                }`}
                style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
                onClick={handleBookClick}
                disabled={!isFormValid || checkingSession}
              >
                {dict.bookNow}
              </button>

              <p className="text-center text-xs text-gray-400 mt-3">
                {dict.noCharge}
              </p>
            </>
          ) : (
            <>
              {guestStep === "form" && guestForm && verified && (
                <form onSubmit={handleGuestFormSubmit} className="space-y-5">
                  {/* ── Checkin / checkout / adults / children, one row ── */}
                  <div className="flex flex-wrap items-end gap-3">
                    <section ref={dateRef} className="relative flex items-end gap-2">
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
                      {dateAndGuestCalendar}
                    </section>

                    <div className="min-w-[92px]">
                      <label className="block text-xs font-medium text-gray-400 mb-1">{dict.adults}</label>
                      <Counter
                        value={adults}
                        min={1}
                        max={5}
                        onDecrement={() => setAdults(adults - 1)}
                        onIncrement={() => setAdults(adults + 1)}
                      />
                    </div>

                    <div className="min-w-[92px]">
                      <label className="block text-xs font-medium text-gray-400 mb-1">{dict.children}</label>
                      <Counter
                        value={children.length}
                        min={0}
                        max={4}
                        onDecrement={removeChild}
                        onIncrement={addChild}
                      />
                    </div>
                  </div>

                  {childAgesBlock}

                  <div className="border-t border-gray-100" />

                  {/* ── Guest details ─────────────────────────────── */}
                  <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-widest">
                    {verified.guestMode === "create" ? dict.modal.guestTitleCreate : dict.modal.guestTitleUpdate}
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <TextField
                      label={dict.modal.firstName}
                      value={guestForm.first_name}
                      onChange={(v) => setGuestForm((p) => (p ? { ...p, first_name: v } : p))}
                    />
                    <TextField
                      label={dict.modal.familyName}
                      value={guestForm.family_name}
                      onChange={(v) => setGuestForm((p) => (p ? { ...p, family_name: v } : p))}
                    />
                    <TextField
                      label={dict.modal.email}
                      type="email"
                      value={guestForm.email}
                      onChange={(v) => setGuestForm((p) => (p ? { ...p, email: v } : p))}
                    />
                    <TextField
                      label={dict.modal.phoneNumber}
                      value={guestForm.phone_number}
                      onChange={(v) => setGuestForm((p) => (p ? { ...p, phone_number: v } : p))}
                    />
                    <TextField
                      label={dict.modal.streetAddress}
                      value={guestForm.residence_address.street_address}
                      onChange={(v) => updateAddress("street_address", v)}
                    />
                    <TextField
                      label={dict.modal.zip}
                      value={guestForm.residence_address.zip}
                      onChange={(v) => updateAddress("zip", v)}
                    />
                    <TextField
                      label={dict.modal.city}
                      value={guestForm.residence_address.city}
                      onChange={(v) => updateAddress("city", v)}
                    />
                    <TextField
                      label={dict.modal.stateOptional}
                      value={guestForm.residence_address.state ?? ""}
                      onChange={(v) => updateAddress("state", v)}
                      required={false}
                    />
                    <TextField
                      label={dict.modal.country}
                      value={guestForm.residence_address.country}
                      onChange={(v) => updateAddress("country", v)}
                    />
                    <SelectField
                      label={dict.modal.preferredLanguage}
                      value={guestForm.preferred_language ?? ""}
                      noneLabel={dict.modal.noPreference}
                      options={LANGUAGES}
                      onChange={(v) => setGuestForm((p) => (p ? { ...p, preferred_language: (v || null) as Language | null } : p))}
                    />
                    <SelectField
                      label={dict.modal.preferredCurrency}
                      value={guestForm.preferred_currency ?? ""}
                      noneLabel={dict.modal.noPreference}
                      options={CURRENCIES}
                      onChange={(v) => setGuestForm((p) => (p ? { ...p, preferred_currency: (v || null) as Currency | null } : p))}
                    />
                  </div>

                  {formError && <p className="text-sm text-red-600">{formError}</p>}

                  <div className="flex gap-3">
                    <button
                      type="button"
                      onClick={resetBookingFlow}
                      className="flex-1 text-gray-600 font-semibold py-4 rounded-xl text-base transition-all border border-gray-200 hover:bg-gray-50 active:scale-[0.98] cursor-pointer"
                    >
                      {dict.cancel}
                    </button>
                    <button
                      type="submit"
                      disabled={pending || !isFormValid}
                      className="flex-1 text-white font-semibold py-4 rounded-xl text-base transition-all shadow-lg active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                      style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
                    >
                      {dict.bookNow}
                    </button>
                  </div>
                </form>
              )}

              {guestStep === "submitting" && (
                <p className="text-sm text-gray-600 text-center py-8">{dict.modal.submitting}</p>
              )}

              {guestStep === "success" && (
                <div className="text-center py-4 space-y-4">
                  <p className="text-sm text-gray-700">{dict.modal.successMessage.replace("{name}", guestName)}</p>
                  <button
                    type="button"
                    onClick={handleDone}
                    className="w-full text-white font-semibold py-3 rounded-xl text-sm transition-all shadow-lg cursor-pointer"
                    style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
                  >
                    {dict.modal.done}
                  </button>
                </div>
              )}

              {guestStep === "error" && (
                <div className="text-center py-4 space-y-4">
                  <p className="text-sm text-red-600">{formError}</p>
                  <button
                    type="button"
                    onClick={() => setGuestStep("form")}
                    className="w-full text-white font-semibold py-3 rounded-xl text-sm transition-all shadow-lg cursor-pointer"
                    style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
                  >
                    {dict.modal.tryAgain}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {identityModalOpen && (
        <BookingModal
          dict={dict.modal}
          onClose={() => setIdentityModalOpen(false)}
          onVerified={handleVerified}
        />
      )}
    </>
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

/* ── TextField ─────────────────────────────────────────── */
function TextField({
  label,
  value,
  onChange,
  type = "text",
  disabled = false,
  required = true,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  disabled?: boolean;
  required?: boolean;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-gray-500 mb-1">
        {label}
      </label>
      <input
        id={id}
        type={type}
        required={required}
        disabled={disabled}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-teal-300 focus:border-teal-400 disabled:bg-gray-50 disabled:text-gray-400"
      />
    </div>
  );
}

/* ── SelectField ───────────────────────────────────────── */
function SelectField({
  label,
  value,
  options,
  noneLabel,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  noneLabel: string;
  onChange: (v: string) => void;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-gray-500 mb-1">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-xl border border-gray-200 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-teal-300 focus:border-teal-400 cursor-pointer"
      >
        <option value="">{noneLabel}</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}
