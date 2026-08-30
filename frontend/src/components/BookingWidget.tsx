"use client";

import { useState, useRef, useId, useEffect, useLayoutEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import { DayPicker } from "react-day-picker";
import type { DateRange, DayButtonProps } from "react-day-picker";
import { format, differenceInCalendarDays, parse, isBefore, isAfter, isSameDay, subDays, addDays } from "date-fns";
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
  createPaymentIntent,
  deleteBooking,
  getFromPrice,
  getGuest,
  getPaymentOutcome,
  getStayQuote,
  listBookings,
  listPublicBookedDateRanges,
  listPublicClosedDateRanges,
  listPublicPlans,
  listPublicPrices,
  listPublicPromotions,
  registerGuestSelf,
  updateBooking,
  updateGuest,
  verifyToken,
  type Currency,
  type FromPriceQuote,
  type GuestInput,
  type Language,
  type PaymentIntentResponse,
  type PaymentOutcome,
  type Plan,
  type PlanQuote,
  type PublicPrice,
  type PublicPromotion,
  type StayQuote,
} from "@/lib/api";
import { findMinStay, hasRateFor, promotionsForDate } from "@/lib/pricing";
import PriceWithDiscount from "@/components/PriceWithDiscount";
import { useLocaleSwitch } from "@/lib/use-locale-switch";
import BookingModal, { guestToForm, type BookingModalDict, type VerifiedIdentity } from "@/components/BookingModal";
import { CancellationTimeline, refundHighlightColor } from "@/components/CancellationTimeline";
import { cheapestPerCancellationFee } from "@/lib/refund";
import PaymentStep from "@/components/PaymentStep";
import { PhoneInput } from "@/components/PhoneInput";
import { isValidPhoneNumber } from "react-phone-number-input";
import { CountrySelect } from "@/components/CountrySelect";
import { isValidCountry } from "@/lib/countries";
import { clearGuestSession, readGuestSession, saveGuestSession } from "@/lib/guest-auth";

const CHILD_AGES = Array.from({ length: 18 }, (_, i) => i);
const DISPLAY_FORMAT = "dd/MM/yyyy";
const DATE_PLACEHOLDER = "DD/MM/YYYY";
const LANGUAGES: Language[] = ["en", "de", "fr", "it"];
const CURRENCIES: Currency[] = ["EUR", "CHF", "USD", "GBP"];
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const DATE_FNS_LOCALES: Record<Locale, DateFnsLocale> = { en: enUS, de, fr, it };
const TRANSITION_MS = 380;
// The calendar breakout's collapse reuses the same ease-out curve as its
// expand by default, but an ease-out curve front-loads most of a shrink's
// size change into its first frames, reading as an abrupt snap rather than
// a smooth collapse — so closing gets its own, slower, standard ease-in-out
// timing instead.
const COLLAPSE_TRANSITION_MS = 560;
const COLLAPSE_EASING = "cubic-bezier(0.4, 0, 0.2, 1)";
// id of the app's real scrollable container (frontend/src/app/[lang]/page.tsx)
const PAGE_SCROLL_ID = "page-scroll";
// sessionStorage key: carries the in-progress date/guest-count selection
// across the full-page navigation that applying a guest's saved
// preferred_language triggers (see handleVerified), so a login that
// switches locale resumes the booking flow instead of dropping it.
const LOCALE_SWITCH_RESUME_KEY = "booking_resume_after_locale_switch";
// Matches the `lg:` breakpoint used throughout this file's className
// strings — kept as a constant since the FLIP effects below need the same
// threshold read from JS (window.innerWidth) to decide whether to run.
const MOBILE_BREAKPOINT_PX = 1024;
// Picking a range fires a render per click, and each one would otherwise
// start its own quote request. Short enough that the guest never notices a
// wait, long enough that a from→to selection costs one request, not two.
const QUOTE_DEBOUNCE_MS = 150;
// Width reserved for a header figure, in `ch` — the width of a "0" in
// whatever size that figure renders at, so one number covers the header's
// mobile (18px) and desktop (20px) sizes alike. Sized for the widest string
// formatPrice can return at four digits: "€1234" measures 4.53ch and
// "1234 CHF" 6.69ch in Geist, so these leave a hair of slack and no more.
// Reserved as a min-width on the figure and used as the loading
// placeholder's width, which is what keeps the "from"/"per night" text
// around it still when a price lands (and when one price replaces another).
const PRICE_SLOT_CH: Record<"CHF" | "other", number> = { CHF: 6.8, other: 4.6 };
const priceSlot = (currency: Currency) => `${PRICE_SLOT_CH[currency === "CHF" ? "CHF" : "other"]}ch`;

// Breathing room the promotion tooltip keeps from the day it describes and
// from the window edges it is clamped against.
const TOOLTIP_GAP = 6;
const TOOLTIP_MARGIN = 8;

type Child = { age: number | null };
/** A stay quote together with what it was fetched for. */
type QuotedStay = { beginDate: string; endDate: string; currency: Currency; quote: StayQuote };
// "confirming" onwards are the states of the one question Stripe cannot
// answer: did this booking actually get its dates? See awaitPaymentOutcome.
type GuestFlowStep =
  | "plan"
  | "form"
  | "submitting"
  | "payment"
  | "confirming"
  | "success"
  | "conflict"
  | "pending"
  | "error";

// How long, and how often, to ask the server what became of a payment the
// guest has just confirmed. Stripe delivers that verdict to us by webhook,
// so it lands a beat after the browser is already done — usually within a
// second or two.
const OUTCOME_POLL_INTERVAL_MS = 1000;
const OUTCOME_POLL_TIMEOUT_MS = 30_000;

export interface BookingDict {
  planYourStay: string;
  yourRateTitle: string;
  yourDataTitle: string;
  paymentDetailsTitle: string;
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
  back: string;
  noCharge: string;
  resumePendingBookingPrompt: string;
  datesTakenMessage: string;
  total: string;
  specialOffer: string;
  regularPrice: string;
  youSave: string;
  promotionPercentTooltip: string;
  promotionAmountTooltip: string;
  modal: BookingModalDict;
}

export default function BookingWidget({ dict, lang }: { dict: BookingDict; lang: Locale }) {
  const today = new Date();
  const dateFnsLocale = DATE_FNS_LOCALES[lang];
  const { currency, setCurrency } = useCurrency();
  const switchLocale = useLocaleSwitch();
  const [range, setRange] = useState<DateRange | undefined>();
  const [hoverDate, setHoverDate] = useState<Date | undefined>(undefined);
  const [calendarOpen, setCalendarOpen] = useState(false);
  // Stays mounted slightly longer than calendarOpen on close (cleared by
  // the breakout FLIP effect's settle(), once the collapse animation
  // actually finishes) — so the calendar is still there to be visibly
  // clipped away by the shrinking box, instead of vanishing instantly the
  // moment calendarOpen flips.
  const [calendarMounted, setCalendarMounted] = useState(false);
  if (calendarOpen && !calendarMounted) setCalendarMounted(true);
  const [adults, setAdults] = useState(2);
  const [children, setChildren] = useState<Child[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [prices, setPrices] = useState<PublicPrice[]>([]);
  const [bookedRanges, setBookedRanges] = useState<DateRange[]>([]);
  // Active offers covering future dates — drives the calendar's violet
  // highlight and its tooltip. Carries no stay price: what a stay costs
  // comes from `quote` below.
  const [promotions, setPromotions] = useState<PublicPromotion[]>([]);
  // Every price this widget shows, computed server-side. `quoteResult`
  // covers the picked dates (one entry per plan); `fromPrice` is the
  // "from …/night" teaser shown before any dates are picked. Nothing here is
  // multiplied on the client — see lib/pricing.ts.
  //
  // The quote is stored together with what it was fetched for, so a quote
  // that no longer describes the current selection can be recognised and
  // ignored rather than having to be cleared (see `quote` below).
  const [quoteResult, setQuoteResult] = useState<QuotedStay | null>(null);
  const [fromPrice, setFromPrice] = useState<FromPriceQuote | null>(null);
  const [identityModalOpen, setIdentityModalOpen] = useState(false);
  const dateRef = useRef<HTMLDivElement>(null);
  const calendarRef = useRef<HTMLDivElement>(null);
  const widgetRef = useRef<HTMLDivElement>(null);
  // Reserves flow space matching the widget's current on-screen height
  // whenever it has broken out of flow (calendarOpen breakout) — pushes
  // later page content (the highlights section) down as it expands, and
  // lets it settle back up as it collapses. See the ResizeObserver effect
  // below.
  const spacerRef = useRef<HTMLDivElement>(null);
  // Rect captured live (via captureRect()) right before extended toggles, so
  // the FLIP effect below knows where to animate from.
  const prevRectRef = useRef<DOMRect | null>(null);
  // Same idea, but captured right before calendarOpen toggles (compact mode
  // only) — feeds the horizontal breakout FLIP effect further below.
  const prevCompactRectRef = useRef<DOMRect | null>(null);

  // ── Post-OTP booking procedure ──────────────────────────
  const [verified, setVerified] = useState<VerifiedIdentity | null>(null);
  const [guestForm, setGuestForm] = useState<GuestInput | null>(null);
  // Must default to "plan", not "form": handleVerified sets `verified`/
  // `guestForm` before it awaits resumePendingBooking, so React can commit a
  // render in between where the widget is already extended but the plan
  // hasn't been resolved yet (selectedPlanId is still null). Defaulting to
  // "form" let that in-between render show the guest-details step — already
  // pre-filled for a returning guest, and gated only on isFormValid/
  // isGuestDetailsValid (neither of which checks selectedPlan) — so its Next
  // button was live and, once selectedPlan resolved moments later, a click
  // right then would submit straight through to payment, skipping the plan
  // step (and effectively the guest-details step too, since the guest never
  // meant to submit it) entirely.
  const [guestStep, setGuestStep] = useState<GuestFlowStep>("plan");
  const [pending, setPending] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [paymentIntent, setPaymentIntent] = useState<PaymentIntentResponse | null>(null);
  // Set once the booking has been created server-side; a later submit (e.g.
  // after using Back from the payment step) updates this booking in place
  // instead of creating a duplicate.
  const [bookingId, setBookingId] = useState<string | null>(null);
  // The bearer token that created `bookingId`, kept so later calls about the
  // booking authenticate as its owner. Not always verified.authToken: a
  // first-time guest reaches the form on a "pending_guest" token, and
  // registering them mints a new, guest-bound one that submitBooking uses
  // from then on. Only that one passes the booking's ownership check.
  const [bookingToken, setBookingToken] = useState<string | null>(null);
  // True while a stored guest session's bearer token is being validated
  // against the API in response to a Book click.
  const [checkingSession, setCheckingSession] = useState(false);
  // The widget's pinned top once settled into (or out of) extended mode — its
  // top edge never moves, only left/width/height animate. Reused (along with
  // pinnedRight) for the calendar-open breakout below; the two never overlap
  // since that breakout only ever runs while !extended.
  const [pinnedTop, setPinnedTop] = useState<number | null>(null);
  const [pinnedRight, setPinnedRight] = useState<number | null>(null);
  const extended = verified !== null;

  const captureRect = () => {
    if (widgetRef.current) prevRectRef.current = widgetRef.current.getBoundingClientRect();
  };

  const captureCompactRect = () => {
    if (widgetRef.current) prevCompactRectRef.current = widgetRef.current.getBoundingClientRect();
  };

  // Re-run every time the calendar is opened (see toggleCalendar below), not
  // just on mount — bookings/closures made elsewhere while this page stays
  // open must still show up as soon as the guest opens the picker again.
  const fetchAvailability = () => {
    // end_date is the checkout day (exclusive, same convention as
    // hasRateFor), so the last disabled night is the day before it — this
    // keeps a booking's checkout day available as another's check-in. Dates
    // closed off on other platforms use the same convention and are merged
    // into the same disabled-ranges list as actual bookings.
    const toDateRange = (r: { begin_date: string; end_date: string }) => ({
      from: parse(r.begin_date, "yyyy-MM-dd", new Date()),
      to: subDays(parse(r.end_date, "yyyy-MM-dd", new Date()), 1),
    });
    // Promotions ride along: they're read straight off the same calendar,
    // and an offer created or ended elsewhere while this page stays open
    // must show up as soon as the guest reopens the picker.
    Promise.all([
      listPublicBookedDateRanges().catch(() => []),
      listPublicClosedDateRanges().catch(() => []),
      listPublicPromotions(currency).catch(() => []),
    ]).then(([bookedRanges, closedRanges, activePromotions]) => {
      setBookedRanges([...bookedRanges, ...closedRanges].map(toDateRange));
      setPromotions(activePromotions);
    });
  };

  useEffect(() => {
    listPublicPlans()
      .then(setPlans)
      .catch(() => setPlans([]));
  }, []);

  // Keyed on `currency` rather than run once: a promotion's discount amount
  // is converted server-side, so switching currency has to re-read it — the
  // same reason the price list below is re-fetched.
  useEffect(() => {
    fetchAvailability();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currency]);

  // Prices are only consulted for *availability* now (which days are
  // bookable, and the hard minimum stay) — every figure the guest sees comes
  // from the quote endpoints below. They are still fetched per currency
  // because min_stay_days lives on the same documents.
  useEffect(() => {
    listPublicPrices(currency)
      .then(setPrices)
      .catch(() => setPrices([]));
  }, [currency]);

  // The "from …/night" teaser: the cheapest future nightly rate at the
  // cheapest plan's ratio, with the best offer on it — all resolved on the
  // server (see backend/app/api/routes/quotes.py).
  useEffect(() => {
    const controller = new AbortController();
    getFromPrice(currency, controller.signal)
      .then(setFromPrice)
      .catch(() => {
        if (!controller.signal.aborted) setFromPrice(null);
      });
    return () => controller.abort();
  }, [currency]);

  // The dates to quote for, in the server's own format. Also the key that
  // decides whether a quote already in hand still describes what's on screen.
  const quoteBeginDate = range?.from ? format(range.from, "yyyy-MM-dd") : null;
  const quoteEndDate = range?.to ? format(range.to, "yyyy-MM-dd") : null;

  // The priced answer for the picked dates, for every plan at once.
  // Debounced so a from→to selection costs one request, and aborted so a
  // fast re-pick can't let an older answer land after a newer one.
  useEffect(() => {
    if (!quoteBeginDate || !quoteEndDate) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      getStayQuote(quoteBeginDate, quoteEndDate, currency, controller.signal)
        .then((stayQuote) =>
          setQuoteResult({
            beginDate: quoteBeginDate,
            endDate: quoteEndDate,
            currency,
            quote: stayQuote,
          })
        )
        .catch(() => {
          // Aborted (superseded) or failed: either way the stale result
          // below stops matching, so the spinner shows rather than a wrong
          // figure. Nothing to record.
        });
    }, QUOTE_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [quoteBeginDate, quoteEndDate, currency]);

  // A quote counts only while it still describes the current selection: one
  // fetched for other dates, or in another currency, reads as absent — which
  // is what makes the price placeholder show instead of a figure that no
  // longer matches what's on screen.
  const quote =
    quoteResult !== null &&
    quoteResult.beginDate === quoteBeginDate &&
    quoteResult.endDate === quoteEndDate &&
    quoteResult.currency === currency
      ? quoteResult.quote
      : null;

  // Shared by every check-in/check-out DateField below: opening the calendar
  // always refreshes availability first, so it can never show data staler
  // than the last time it was opened.
  const toggleCalendar = () => {
    captureCompactRect();
    setCalendarOpen((v) => {
      const next = !v;
      if (next) fetchAvailability();
      return next;
    });
  };

  // Close calendar on outside click. Guarded on calendarOpen (and thus
  // re-subscribed whenever it changes, to see a fresh value rather than a
  // stale one closed over at mount) — without it, this fired on *every*
  // click anywhere on the page while dateRef/calendarRef are both null
  // (i.e. the whole time the widget is in its extended, post-login flow,
  // since that JSX branch doesn't render the date-picker section at all),
  // because `null?.contains(...)` is vacuously falsy and never short-circuits
  // the check below. Each such click called captureCompactRect(), stashing
  // the widget's *current* (extended-mode) rect as if it were its compact
  // one; Cancel later reading that stale rect raced the calendar-breakout
  // effect against the real collapse animation and left a stale flow
  // spacer reserving extra page height after the widget had already shrunk.
  useEffect(() => {
    if (!calendarOpen) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (dateRef.current?.contains(target)) return;
      if (calendarRef.current?.contains(target)) return;
      captureCompactRect();
      setCalendarOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [calendarOpen]);

  // Animate the widget moving/resizing between its compact and extended
  // layouts on desktop (FLIP: freeze at the pre-toggle rect, then transition
  // to the natural post-toggle rect). The top edge is pinned to the same
  // value in both keyframes, so only left/width/height ever animate.
  //
  // On mobile, extended mode isn't a floating overlay at all — it's a
  // plain, full-width block in the normal document flow (see the className
  // below), so the page itself grows/shrinks and scrolls along with it.
  // None of this FLIP/fixed-position machinery applies there; just drop any
  // leftover inline positioning from a previous run (e.g. the viewport was
  // resized past the breakpoint) and let CSS handle it.
  useLayoutEffect(() => {
    const el = widgetRef.current;
    const fromRect = prevRectRef.current;
    prevRectRef.current = null;
    if (!el) return;

    if (window.innerWidth < MOBILE_BREAKPOINT_PX) {
      el.style.cssText = "";
      setPinnedTop(null);
      setPinnedRight(null);
      return;
    }
    if (!fromRect) return;

    // A still-settled previous transition deliberately leaves position/top
    // (or left/right) pinned inline — clear that out before measuring,
    // otherwise a stale `position:fixed` combined with this render's
    // className (which may now specify a plain `w-full`, resolving against
    // the *viewport* while still fixed) can measure a nonsensical,
    // over-constrained box instead of the element's true target size.
    el.style.cssText = "";
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
      // Clear everything EXCEPT position/top when extended — those two stay
      // pinned via direct DOM mutation (already holding the correct frozen
      // value from above) right up until the setPinnedTop below lands and
      // the style prop takes over on React's next render. Clearing them
      // here too would leave a gap, rendered via a plain event listener
      // outside React's commit cycle, where the element is position:fixed
      // with no top offset — falling back to CSS's "static position"
      // default and visibly jumping before snapping to the right spot.
      el.style.transition = "";
      el.style.left = "";
      el.style.right = "";
      el.style.width = "";
      el.style.height = "";
      el.style.maxWidth = "";
      el.style.maxHeight = "";
      el.style.overflow = "";
      el.style.zIndex = "";
      el.style.transform = "";
      el.style.translate = "";
      if (!extended) {
        el.style.position = "";
        el.style.top = "";
      }
      setPinnedTop(extended ? top : null);
      // This transition always supersedes any horizontal breakout pin from
      // the calendar-open effect below (the two never run concurrently,
      // since that effect no-ops while extended).
      setPinnedRight(null);
    };
    el.addEventListener("transitionend", settle, { once: true });

    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener("transitionend", settle);
    };
  }, [extended]);

  // Animate the widget growing/shrinking to fit the embedded calendar —
  // breaking out of its fixed-width grid column horizontally as well as
  // growing vertically, in one continuous motion (both width and height
  // animate together here, same as the extended-mode FLIP above, so the
  // bottom-left corner moves smoothly instead of resizing in two separate
  // steps). The invariant is top+right (not just top): the widget grows
  // leftward/downward from its original top-right corner.
  //
  // Positioned absolute (not fixed) relative to #page-scroll — the app's
  // real scroll container (made `relative` in page.tsx specifically so it
  // becomes this containing block) — rather than the viewport. That way, if
  // the calendar makes the widget taller than the viewport, #page-scroll's
  // own scrollable area grows to fit it and the *page* scrolls, instead of
  // the widget clipping/scrolling its own content internally.
  useLayoutEffect(() => {
    const el = widgetRef.current;
    const fromRect = prevCompactRectRef.current;
    prevCompactRectRef.current = null;
    if (!el || !fromRect || extended) return;
    const scrollContainer = document.getElementById(PAGE_SCROLL_ID);
    if (!scrollContainer) return;

    // Below page.tsx's hero `lg` breakpoint (where its grid collapses to a
    // single column), the widget already spans close to the full width, so
    // growing it further from a right anchor reads as lopsided — center it
    // instead, the same way extended mode's overlay centers (className
    // below adds `left-1/2 -translate-x-1/2` only under that breakpoint).
    const isMobile = window.innerWidth < 1024;

    // Same reasoning as the extended-mode effect above: clear any leftover
    // pinned position/top/right(/left) before measuring, so a stale
    // `position:absolute` from the settled-open state doesn't get combined
    // with this render's (now plain `w-full`) className into a bogus
    // over-constrained target size when closing.
    el.style.cssText = "";
    // When closing, the calendar panel is deliberately still mounted (see
    // calendarMounted) so it stays visible, clipped away by the shrinking
    // box, instead of vanishing before the shrink even starts — but that
    // means it would also still count toward this auto-height measurement.
    // Hide it just for this one synchronous read, then restore it so the
    // rest of the effect (and the animation) sees it as present.
    const calendarEl = calendarRef.current;
    const prevCalendarDisplay = calendarEl?.style.display ?? "";
    if (!calendarOpen && calendarEl) calendarEl.style.display = "none";
    const toRect = el.getBoundingClientRect();
    if (!calendarOpen && calendarEl) calendarEl.style.display = prevCalendarDisplay;
    const containerRect = scrollContainer.getBoundingClientRect();
    // Convert from viewport-relative (getBoundingClientRect) to
    // container-content-relative (position:absolute) coordinates — top
    // needs the container's current scroll added back in; right/left don't,
    // since #page-scroll only ever scrolls vertically.
    const top = fromRect.top - containerRect.top + scrollContainer.scrollTop;
    const right = containerRect.right - fromRect.right;
    const left = fromRect.left - containerRect.left;

    el.style.transition = "none";
    el.style.position = "absolute";
    el.style.top = `${top}px`;
    if (isMobile) {
      // Raw pixel left for the animation itself — same trick the
      // extended-mode FLIP uses.
      el.style.left = `${left}px`;
      el.style.right = "auto";
    } else {
      el.style.right = `${right}px`;
      el.style.left = "auto";
    }
    el.style.width = `${fromRect.width}px`;
    el.style.height = `${fromRect.height}px`;
    el.style.maxWidth = "none";
    el.style.maxHeight = "none";
    el.style.overflow = "hidden";
    el.style.zIndex = "91";
    // Cancel any className-driven centering transform (Tailwind v4's
    // -translate-x-1/2 uses the standalone `translate` property, not
    // `transform`) so it doesn't also shift the absolute `left` above.
    el.style.transform = "none";
    el.style.translate = "none";
    void el.offsetHeight;

    const raf = requestAnimationFrame(() => {
      const [duration, easing] = calendarOpen
        ? [TRANSITION_MS, "cubic-bezier(0.22, 1, 0.36, 1)"]
        : [COLLAPSE_TRANSITION_MS, COLLAPSE_EASING];
      const props = isMobile ? ["left", "width", "height"] : ["width", "height"];
      el.style.transition = props
        .map((prop) => `${prop} ${duration}ms ${easing}`)
        .join(", ");
      if (isMobile) el.style.left = `${toRect.left - containerRect.left}px`;
      el.style.width = `${toRect.width}px`;
      el.style.height = `${toRect.height}px`;
    });

    const settle = () => {
      // Same reasoning as the extended-mode settle above: leave
      // position/top/right(/left) pinned via direct DOM mutation (already
      // holding the correct frozen values from above) through the gap
      // until the setPinnedTop/setPinnedRight calls below land on React's
      // next render — clearing them here too would let the browser paint
      // one frame with position:fixed but no offsets, falling back to a
      // "static position" and visibly jumping before snapping back. On
      // mobile, `left` is cleared immediately instead — the className's
      // `left-1/2 -translate-x-1/2` is self-sufficient with no gap, same
      // as extended mode's own centering.
      el.style.transition = "";
      el.style.left = "";
      el.style.width = "";
      el.style.height = "";
      el.style.maxWidth = "";
      el.style.maxHeight = "";
      el.style.overflow = "";
      el.style.zIndex = "";
      el.style.transform = "";
      el.style.translate = "";
      if (!calendarOpen) {
        el.style.position = "";
        el.style.top = "";
        el.style.right = "";
        // Only now — once the collapse has actually finished — remove the
        // calendar panel from the tree for good.
        setCalendarMounted(false);
      }
      setPinnedTop(calendarOpen ? top : null);
      setPinnedRight(calendarOpen && !isMobile ? right : null);
    };
    el.addEventListener("transitionend", settle, { once: true });

    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener("transitionend", settle);
    };
  }, [calendarOpen, extended]);

  // Keep the flow spacer's height matched to the widget's actual rendered
  // height while it's broken out of flow (calendarOpen breakout uses
  // position:absolute; extended's own overlay uses position:fixed, so it's
  // naturally excluded here) — ResizeObserver fires on every real layout
  // change, including each frame of the FLIP transition above, so this
  // tracks the widget's grow/shrink animation smoothly without needing a
  // transition of its own. Checking the widget's *live* inline style
  // (rather than the calendarOpen/extended state directly) matters for the
  // closing case specifically: calendarOpen already flips to false before
  // the shrink animation finishes, but the widget stays position:absolute,
  // still shrinking, until its own settle() runs at the very end — so the
  // spacer keeps tracking it down smoothly instead of snapping to 0 early.
  useLayoutEffect(() => {
    const widget = widgetRef.current;
    const spacer = spacerRef.current;
    if (!widget || !spacer) return;
    const update = () => {
      const breakout = widget.style.position === "absolute";
      spacer.style.height = breakout ? `${widget.getBoundingClientRect().height}px` : "0px";
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(widget);
    return () => observer.disconnect();
  }, [calendarOpen, extended]);

  // Auto-close the calendar once both dates are chosen
  useEffect(() => {
    if (range?.from && range?.to) {
      captureCompactRect();
      setCalendarOpen(false);
    }
  }, [range]);

  const checkInText = range?.from ? format(range.from, DISPLAY_FORMAT) : "";
  const checkOutText = range?.to ? format(range.to, DISPLAY_FORMAT) : "";

  const checkInMinStay = range?.from ? findMinStay(prices, format(range.from, "yyyy-MM-dd")) : 1;

  const nights =
    range?.from && range?.to ? differenceInCalendarDays(range.to, range.from) : 0;
  const totalGuests = adults + children.length;
  const selectedPlan = plans.find((p) => p._id === selectedPlanId) ?? null;
  const visiblePlans = range?.from
    ? cheapestPerCancellationFee(plans, differenceInCalendarDays(range.from, today))
    : plans;

  // Every figure below is read straight out of the server's answer — the
  // widget formats, it never multiplies. `quote` is null while a request is
  // in flight (or before dates are picked), which is what makes the price
  // placeholder show rather than a stale number.
  const planQuoteFor = (planId: string | null): PlanQuote | null =>
    quote?.plans.find((p) => p.plan_id === planId) ?? null;
  const selectedPlanQuote = planQuoteFor(selectedPlanId);
  // Cheapest plan, for the "from …" framing the header uses until the guest
  // has actually chosen a rate.
  const cheapestPlanQuote =
    quote?.plans.reduce<PlanQuote | null>((min, p) => (min === null || p.price < min.price ? p : min), null) ??
    null;
  const headerQuote = selectedPlanQuote ?? cheapestPlanQuote;
  // Before any dates are picked there is no stay to price, so the header
  // shows the per-night teaser instead of a total.
  const headerPrice = nights > 0 ? headerQuote?.price ?? null : fromPrice?.price_per_night ?? null;
  const headerRegularPrice =
    nights > 0 ? headerQuote?.regular_price ?? null : fromPrice?.regular_price_per_night ?? null;
  const headerPriceChf = nights > 0 ? headerQuote?.price_chf ?? null : fromPrice?.price_per_night_chf ?? null;
  const headerRegularPriceChf =
    nights > 0 ? headerQuote?.regular_price_chf ?? null : fromPrice?.regular_price_per_night_chf ?? null;
  // Which stage of the extended flow (rate → data → payment) the header
  // should reflect; falls back to the initial planYourStay/"from" price
  // outside the extended flow and on the terminal success/error screens.
  const headerTitle = !extended
    ? dict.planYourStay
    : guestStep === "plan"
    ? dict.yourRateTitle
    : guestStep === "form"
    ? dict.yourDataTitle
    : guestStep === "submitting" || guestStep === "payment"
    ? dict.paymentDetailsTitle
    : guestStep === "confirming"
    ? dict.modal.confirmingTitle
    : guestStep === "conflict"
    ? dict.modal.conflictTitle
    : guestStep === "pending"
    ? dict.modal.pendingTitle
    : dict.planYourStay;
  const showFromPrefix = (!extended || guestStep === "plan") && !selectedPlan;
  // A stay that was never granted has no price to quote. Leaving the total
  // in the header of the "dates are gone" screen reads as a sum the guest
  // owes, right beside the line telling them they owe nothing.
  const showHeaderPrice = guestStep !== "conflict";
  const isFormValid =
    !!range?.from &&
    !!range?.to &&
    nights >= checkInMinStay &&
    children.every((child) => child.age !== null);
  // Gates the guest-details step's Next button: every mandatory "Your data"
  // field (state/preferred language/preferred currency are all optional)
  // has to hold a genuinely valid value, not just something non-empty —
  // otherwise the native HTML validation popup on submit is the only thing
  // catching a typo, after the guest already thought they were done.
  const isGuestDetailsValid =
    !!guestForm &&
    guestForm.first_name.trim() !== "" &&
    guestForm.family_name.trim() !== "" &&
    EMAIL_RE.test(guestForm.email.trim()) &&
    isValidPhoneNumber(guestForm.phone_number || "") &&
    guestForm.residence_address.street_address.trim() !== "" &&
    guestForm.residence_address.zip.trim() !== "" &&
    guestForm.residence_address.city.trim() !== "" &&
    isValidCountry(guestForm.residence_address.country);

  // animate is false only for the locale-switch resume effect below: that
  // call happens milliseconds after the page's very first paint, before
  // layout/images/fonts have settled, so the compact-widget rect captureRect()
  // would grab there isn't reliable — animating a grow-from-compact FLIP off
  // of it left the widget stuck mid-transition (a small clipped box with
  // stale inline styles that never got cleaned up). There's no compact state
  // the guest actually saw on this fresh page anyway, so skipping the
  // animation and opening straight into the natural extended layout is both
  // safer and correct.
  // checkInOverride exists for the locale-switch resume below: that caller
  // runs on a freshly mounted widget and has the restored check-in date in
  // hand, while this closure's own `range` is still at its initial value.
  const handleVerified = async (
    identity: VerifiedIdentity,
    animate = true,
    checkInOverride?: Date
  ) => {
    const preferredLanguage = identity.guestForm.preferred_language;
    if (preferredLanguage && preferredLanguage !== lang) {
      // The guest's saved language differs from the page they're on — their
      // profile is authoritative, so always switch, whether or not dates are
      // selected yet. switchLocale navigates to a new locale route, which
      // remounts this whole widget — so rather than opening the extended
      // guest-details view here and having it immediately collapse away
      // underneath the navigation (then reopen on the new page once
      // resumed), stash the already-verified identity plus the date/guest-
      // count selection and switch first. The mount effect below restores
      // everything and opens the widget once, directly on the correct
      // locale — a single transition instead of open → close → reopen.
      // checkIn/checkOut are omitted when no dates are selected yet — the
      // resume effect leaves the range empty in that case.
      window.sessionStorage.setItem(
        LOCALE_SWITCH_RESUME_KEY,
        JSON.stringify({
          identity,
          checkIn: range?.from ? format(range.from, "yyyy-MM-dd") : null,
          checkOut: range?.to ? format(range.to, "yyyy-MM-dd") : null,
          adults,
          children: children.map((c) => c.age),
        })
      );
      setIdentityModalOpen(false);
      switchLocale(preferredLanguage);
      return;
    }

    if (animate) captureRect();
    setVerified(identity);
    setGuestForm(identity.guestForm);
    setFormError(null);
    setIdentityModalOpen(false);
    saveGuestSession({
      token: identity.authToken,
      guestId: identity.guestId,
      guestMode: identity.guestMode,
      isAdminBooking: identity.isAdminBooking,
      expiresAt: identity.expiresAt,
    });

    // Not for an admin booking on a guest's behalf: identity.authToken is
    // then the admin's own (sees every booking in the system, not just this
    // guest's), and the admin is starting a fresh booking for whichever
    // guest they just picked, not resuming their own checkout.
    if (!identity.isAdminBooking && (await resumePendingBooking(identity))) return;

    // Preselect the default rate. On the locale-switch resume this runs on a
    // fresh mount, in the same commit as the effect that fetches the plans —
    // so reading the `plans`/`range` state here would see both at their
    // initial (empty) values, preselect nothing, and leave the plan step
    // with a permanently disabled Next button. Fetch the plans the same way
    // resumePendingBooking does, and take the check-in date from the caller.
    const availablePlans = plans.length > 0 ? plans : await listPublicPlans().catch(() => plans);
    if (availablePlans !== plans) setPlans(availablePlans);
    const checkIn = checkInOverride ?? range?.from;
    const selectablePlans = checkIn
      ? cheapestPerCancellationFee(availablePlans, differenceInCalendarDays(checkIn, today))
      : availablePlans;
    setSelectedPlanId(selectablePlans[0]?._id ?? null);
    setGuestStep("plan");
  };

  // Only one Pending booking is allowed per guest at a time (enforced
  // server-side — see app.api.routes.bookings.create_booking), so a guest
  // who's already partway through checkout is meant to finish (or cancel)
  // that one rather than start another. Called right after a guest's
  // identity resolves (fresh OTP verify or a resumed session): if they have
  // a Pending booking, jump straight into its guest-details step (skipping
  // only the plan step, since the plan is already known from the pending
  // booking) instead of starting the usual flow over from scratch. Payment
  // itself is intentionally NOT skipped to — the guest still needs to review
  // their details before paying, same as any fresh booking. Returns whether
  // it resumed.
  const resumePendingBooking = async (identity: VerifiedIdentity): Promise<boolean> => {
    const bookings = await listBookings(identity.authToken);
    const pendingBooking = bookings.find((b) => b.status === "Pending");
    if (!pendingBooking) return false;

    // Let the guest choose rather than silently dropping them into checkout
    // for a booking they may not even remember starting. Declining deletes
    // it outright — only one Pending booking is allowed per guest at a
    // time, so keeping it around unconfirmed would just block a fresh one.
    if (!window.confirm(dict.resumePendingBookingPrompt)) {
      await deleteBooking(pendingBooking._id, identity.authToken).catch(() => {});
      return false;
    }

    // Fetched fresh here rather than trusting the `plans` state: this can
    // run from the silent mount-time auto-resume effect below, whose
    // closure was formed before that effect's own listPublicPlans() call
    // had a chance to land, so reading the state var there would always see
    // the pre-fetch empty array.
    //
    // No payment intent is created here — submitBooking creates one once the
    // guest actually submits the guest-details step below, same as a fresh
    // booking. Creating one now would go unused and leave an orphan Stripe
    // intent, since submitBooking would just create a fresh one anyway. That
    // also means the "dates got claimed by another guest's payment" 409 (see
    // submitBooking) surfaces there instead of here.
    const availablePlans = await listPublicPlans().catch(() => plans);
    const beginDates = pendingBooking.date_ranges.map((r) => parse(r.begin_date, "yyyy-MM-dd", new Date()));
    const endDates = pendingBooking.date_ranges.map((r) => parse(r.end_date, "yyyy-MM-dd", new Date()));
    setRange({
      from: beginDates.reduce((min, d) => (d < min ? d : min)),
      to: endDates.reduce((max, d) => (d > max ? d : max)),
    });
    setBookingId(pendingBooking._id);
    setBookingToken(identity.authToken);
    setPlans(availablePlans);
    // Bookings don't store a plan id, only a snapshot of the cancellation
    // policy they were made under — match it back to a current plan so
    // the rate shows as selected if the guest goes Back to the plan step,
    // and so the header price can resolve instead of spinning forever
    // with no plan selected.
    const matchedPlan = availablePlans.find(
      (p) => p.cancellation_policy.name === pendingBooking.cancellation_policy.name
    );
    setSelectedPlanId(matchedPlan?._id ?? null);
    setGuestStep("form");
    return true;
  };

  // Shared by resumeFromSession and the mount-time pending-booking check
  // below: confirms a stored session's bearer token is still accepted
  // server-side and resolves it to a full guest profile. Returns null if
  // the token's rejected/expired, or if verification was completed last
  // time but registration was abandoned before a guest profile existed —
  // callers fall back to a fresh OTP flow in that case, which re-resolves
  // subject_type/guestId and pre-fills correctly if a guest exists by now.
  const resolveSessionIdentity = async (
    session: NonNullable<ReturnType<typeof readGuestSession>>
  ): Promise<VerifiedIdentity | null> => {
    await verifyToken(session.token);
    if (!session.guestId) return null;
    const guest = await getGuest(session.guestId, session.token);
    return {
      authToken: session.token,
      expiresAt: session.expiresAt,
      guestId: guest._id,
      guestMode: "update",
      isAdminBooking: false,
      guestForm: guestToForm(guest, lang),
    };
  };

  // Shared by handleBookClick: validates a stored guest session against the
  // API and, if it still resolves to a guest profile, jumps straight into
  // the guest-details step with it. Returns whether it resumed, so callers
  // can fall back to the identifier/OTP modal otherwise.
  const resumeFromSession = async (session: ReturnType<typeof readGuestSession>) => {
    if (!session) return false;
    setCheckingSession(true);
    try {
      const identity = await resolveSessionIdentity(session);
      if (!identity) {
        clearGuestSession();
        return false;
      }
      handleVerified(identity);
      return true;
    } catch {
      // Token rejected or expired server-side — fall back to OTP below.
      clearGuestSession();
      return false;
    } finally {
      setCheckingSession(false);
    }
  };

  // A guest who's already logged in (a stored session, from a previous
  // visit) and has a Pending booking should land straight on its payment
  // step the instant the page loads — not only once they pick dates and
  // click Book, which is the click-triggered case resumeFromSession (via
  // handleBookClick) covers. Silent: a missing/expired session, an
  // admin-booking session (see the isAdminBooking check inside
  // handleVerified above — this mirrors it), or simply no pending booking
  // all leave the widget in its normal idle state.
  useEffect(() => {
    if (window.sessionStorage.getItem(LOCALE_SWITCH_RESUME_KEY)) return; // handled below instead
    const session = readGuestSession();
    if (!session || session.isAdminBooking) return;
    (async () => {
      try {
        const identity = await resolveSessionIdentity(session);
        if (!identity) return;
        if (await resumePendingBooking(identity)) {
          setVerified(identity);
          setGuestForm(identity.guestForm);
        }
      } catch {
        // Token rejected/expired — resumeFromSession will clear it and
        // fall back to OTP once the guest actually tries to book.
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Restores the date/guest-count selection and already-verified identity
  // that handleVerified stashed away just before switching to the guest's
  // preferred-language locale, and reopens the widget directly on the
  // correct step — this mount only ever happens right after that switch, so
  // handleVerified's own preferredLanguage/lang check above will now match
  // and open the widget normally instead of switching again.
  useEffect(() => {
    const raw = window.sessionStorage.getItem(LOCALE_SWITCH_RESUME_KEY);
    if (!raw) return;
    window.sessionStorage.removeItem(LOCALE_SWITCH_RESUME_KEY);
    try {
      const resume = JSON.parse(raw) as {
        identity: VerifiedIdentity;
        checkIn: string | null;
        checkOut: string | null;
        adults: number;
        children: (number | null)[];
      };
      const resumedCheckIn = resume.checkIn ? parse(resume.checkIn, "yyyy-MM-dd", new Date()) : undefined;
      if (resumedCheckIn && resume.checkOut) {
        setRange({
          from: resumedCheckIn,
          to: parse(resume.checkOut, "yyyy-MM-dd", new Date()),
        });
      }
      setAdults(resume.adults);
      setChildren(resume.children.map((age) => ({ age })));
      // The restored check-in goes in explicitly: setRange above only takes
      // effect on the next render, so handleVerified's own `range` is still
      // empty and it would otherwise pick the rate for no dates at all.
      handleVerified(resume.identity, false, resumedCheckIn);
    } catch {
      // Malformed/stale payload — nothing to restore.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleBookClick = async () => {
    if (!isFormValid) return;
    const session = readGuestSession();
    if (session && (await resumeFromSession(session))) return;
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

  const resetBookingFlow = () => {
    captureRect();
    setVerified(null);
    setGuestForm(null);
    setSelectedPlanId(null);
    setGuestStep("plan");
    setFormError(null);
    setPending(false);
    setPaymentIntent(null);
    setBookingId(null);
    setBookingToken(null);
  };

  const handleDone = () => {
    resetBookingFlow();
    setRange(undefined);
    setAdults(2);
    setChildren([]);
  };

  // Used by every guest-facing Cancel action (as opposed to resetBookingFlow
  // alone, which also backs the post-success "Done" and dates-taken-conflict
  // paths, where the booking is either legitimate or already gone
  // server-side and must NOT be deleted here). Deletion is fire-and-forget:
  // the UI resets immediately, and a booking that's somehow already gone
  // (e.g. a stale double-click) is simply ignored.
  const cancelBookingFlow = () => {
    if (bookingId && bookingToken) {
      deleteBooking(bookingId, bookingToken).catch(() => {});
    }
    resetBookingFlow();
  };

  const updateAddress = (field: keyof GuestInput["residence_address"], value: string) => {
    setGuestForm((prev) =>
      prev ? { ...prev, residence_address: { ...prev.residence_address, [field]: value } } : prev
    );
  };

  const submitBooking = async (finalGuestId: string, token: string, bookingCurrency: Currency = currency) => {
    if (!selectedPlan || !range?.from || !range?.to) return;
    // Not used to compute anything any more — the backend does that. It
    // stays as a pre-flight check: dates with no configured rate are the
    // one case the backend answers with a 400, and bailing here keeps the
    // guest on the form instead of dropping them into the error screen.
    if (!hasRateFor(prices, format(range.from, "yyyy-MM-dd"))) return;
    setGuestStep("submitting");
    try {
      // No amount is sent: the backend prices the stay from the stored
      // nightly rates and the named plan's ratio, and takes the
      // cancellation policy from that same plan (see
      // backend/app/services/booking_pricing.py). The figures shown above
      // are a quote computed from the same rates via /prices/public, not an
      // input to what is charged.
      const bookingInput = {
        guest_id: finalGuestId,
        plan_name: selectedPlan.name,
        currency: bookingCurrency,
        date_ranges: [
          {
            begin_date: format(range.from, "yyyy-MM-dd"),
            end_date: format(range.to, "yyyy-MM-dd"),
          },
        ],
      };
      // Idempotent: a booking already created earlier in this flow (e.g. the
      // guest used Back from the payment step) is updated in place instead
      // of creating a duplicate.
      const booking = bookingId
        ? await updateBooking(bookingId, token, bookingInput)
        : await createBooking(token, bookingInput);
      setBookingId(booking._id);
      setBookingToken(token);
      const intent = await createPaymentIntent(booking._id, token);
      setPaymentIntent(intent);
      setGuestStep("payment");
    } catch (err) {
      if (err instanceof ApiError && (err.status === 409 || err.status === 404)) {
        // 409: another guest's booking already holds these dates — either
        // detected here, or already recorded by their activation cancelling
        // this booking. 404: this booking is gone entirely (deleted by an
        // admin). Either way the dates are unavailable and there is nothing
        // left to retry into, so tell the guest and close the widget.
        //
        // The message is taken from the dictionary rather than from
        // err.message: the backend's detail is English-only, and this widget
        // is served in four languages.
        window.alert(dict.datesTakenMessage);
        fetchAvailability();
        handleDone();
        return;
      }
      setFormError(err instanceof ApiError ? err.message : String(err));
      setGuestStep("error");
    }
  };

  /**
   * Wait for the server's verdict on a payment Stripe has just accepted,
   * and only then tell the guest anything.
   *
   * Stripe answering the browser means the card cleared — not that the
   * booking is confirmed. A Pending booking doesn't block the calendar, so
   * two guests can be paying for the same nights at once; the booking is
   * granted its dates only when the backend applies the matching webhook,
   * which refuses whoever came second. Rendering the success screen off
   * Stripe's answer alone is what let both of them be told their
   * overlapping stay was reserved.
   *
   * The webhook arrives a beat behind the browser, so this polls until the
   * booking resolves one way or the other. Every exit lands on a step that
   * states what actually happened — never a confirmation the server hasn't
   * given.
   */
  const awaitPaymentOutcome = async () => {
    setGuestStep("confirming");
    if (!bookingId || !bookingToken) {
      setGuestStep("pending");
      return;
    }
    const deadline = Date.now() + OUTCOME_POLL_TIMEOUT_MS;
    for (;;) {
      // A request that fails (an offline blip) is not an outcome — treat it
      // as "not known yet" and keep asking, rather than inventing either a
      // confirmation or a rejection from it. A rejected token is the one
      // failure that will never resolve by asking again, so it stops here
      // instead of burning the whole window on it.
      let outcome: PaymentOutcome;
      try {
        outcome = await getPaymentOutcome(bookingId, bookingToken);
      } catch (err) {
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          setGuestStep("pending");
          return;
        }
        outcome = { state: "pending", detail: null };
      }
      if (outcome.state === "confirmed") {
        setGuestStep("success");
        return;
      }
      if (outcome.state === "conflict") {
        // The nights went to whoever paid first, and this booking is gone
        // (refunded, if anything had been charged). Refresh the calendar so
        // the dates the guest picks next are the ones actually left.
        fetchAvailability();
        setGuestStep("conflict");
        return;
      }
      if (outcome.state === "failed") {
        setFormError(outcome.detail ?? dict.modal.errorTitle);
        setGuestStep("error");
        return;
      }
      if (Date.now() >= deadline) {
        // Still unresolved. Nothing has gone wrong that we know of, so say
        // exactly that — a confirmation email follows if it does go through.
        setGuestStep("pending");
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, OUTCOME_POLL_INTERVAL_MS));
    }
  };

  const handleGuestFormSubmit = async () => {
    if (!verified || !guestForm) return;
    setPending(true);
    setFormError(null);
    try {
      if (verified.guestMode === "create" && verified.isAdminBooking) {
        const { guest, access_token, expires_in } = await createGuest(verified.authToken, guestForm);
        saveGuestSession({
          token: access_token,
          guestId: guest._id,
          guestMode: "create",
          isAdminBooking: true,
          expiresAt: Date.now() + expires_in * 1000,
        });
        if (guestForm.preferred_currency && guestForm.preferred_currency !== currency) {
          setCurrency(guestForm.preferred_currency);
        }
        await submitBooking(guest._id, verified.authToken, guestForm.preferred_currency ?? currency);
      } else if (verified.guestMode === "create") {
        const result = await registerGuestSelf(verified.authToken, guestForm);
        saveGuestSession({
          token: result.access_token,
          guestId: result.guest._id,
          guestMode: "create",
          isAdminBooking: false,
          expiresAt: Date.now() + result.expires_in * 1000,
        });
        // Reflects a currency change from this step immediately (e.g. in the
        // price shown on the payment step that follows). Language isn't
        // switched here — that navigates away from the page mid-checkout,
        // right as booking/payment creation is starting — it's applied on
        // the guest's next visit or login instead (see handleVerified).
        if (guestForm.preferred_currency && guestForm.preferred_currency !== currency) {
          setCurrency(guestForm.preferred_currency);
        }
        await submitBooking(result.guest._id, result.access_token, guestForm.preferred_currency ?? currency);
      } else if (verified.guestMode === "update" && verified.guestId) {
        await updateGuest(verified.guestId, verified.authToken, guestForm);
        if (guestForm.preferred_currency && guestForm.preferred_currency !== currency) {
          setCurrency(guestForm.preferred_currency);
        }
        await submitBooking(verified.guestId, verified.authToken, guestForm.preferred_currency ?? currency);
      }
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : String(err));
      setGuestStep("error");
    } finally {
      setPending(false);
    }
  };

  const childAgesBlock = children.length > 0 && (
    <div className="p-3 bg-green-50 dark:bg-green-950/30 rounded-xl border border-green-100 dark:border-green-800">
      <p className="text-xs font-semibold text-green-700 dark:text-green-400 uppercase tracking-wider mb-3">
        {dict.childrenAges}
      </p>
      <div className="flex flex-wrap gap-3">
        {children.map((child, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
              {dict.child} {i + 1}
            </span>
            <select
              value={child.age ?? ""}
              required
              onChange={(e) =>
                updateChildAge(i, e.target.value === "" ? null : Number(e.target.value))
              }
              className={`text-sm border rounded-lg px-2 py-1.5 bg-white dark:bg-green-950/40 focus:outline-none focus:ring-1 focus:ring-green-300 cursor-pointer ${
                child.age === null
                  ? "border-green-300 dark:border-green-600 text-gray-400 dark:focus:border-green-500 focus:border-green-400"
                  : "border-green-200 dark:border-green-800 text-gray-700 dark:text-gray-300 focus:border-green-500"
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

  const isBookedDate = (date: Date) =>
    bookedRanges.some((r) => r.from && r.to && !isBefore(date, r.from) && !isAfter(date, r.to));

  const isPastDate = (date: Date) => isBefore(date, today) && !isSameDay(date, today);

  const hasNoPrice = (date: Date) => !hasRateFor(prices, format(date, "yyyy-MM-dd"));

  const isOccupiedDate = (date: Date) => isBookedDate(date) || hasNoPrice(date);

  // A stay can't be booked through an occupied (booked or unpriced) night —
  // scans the nights strictly between from/to (both exclusive: from is the
  // check-in night itself, to is the checkout day, neither is "occupied" by
  // this stay).
  const hasOccupiedBetween = (from: Date, to: Date) => {
    let d = addDays(from, 1);
    while (isBefore(d, to)) {
      if (isOccupiedDate(d)) return true;
      d = addDays(d, 1);
    }
    return false;
  };

  // A valid checkout: after check-in, clears its minimum stay, and doesn't
  // cross an occupied date along the way.
  const isValidCheckout = (date: Date) =>
    !!range?.from &&
    isAfter(date, range.from) &&
    differenceInCalendarDays(date, range.from) >= checkInMinStay &&
    !hasOccupiedBetween(range.from, date);

  // While picking a checkout date, dates that aren't valid checkout
  // candidates (too short a stay, or crossing an occupied date) get the
  // "unavailable" tint instead of "available".
  const isInvalidCheckoutCandidate = (date: Date) =>
    !!range?.from && !range?.to && isAfter(date, range.from) && !isValidCheckout(date);

  // A hovered checkout candidate only previews as a valid range when it's
  // itself a valid checkout.
  const hoverIsValidCheckout = !!hoverDate && isValidCheckout(hoverDate);

  // While picking a checkout date, a date that's itself occupied (e.g. the
  // first night of another guest's stay) is still a legitimate checkout —
  // the guest checks out that same morning, before the next stay begins —
  // as long as every night strictly between check-in and it is free. Such
  // dates must stay clickable (not hard-disabled) and get their own
  // "occupied but selectable" tint rather than red.
  const isOccupiedValidCheckout = (date: Date) =>
    !!range?.from && !range?.to && isBookedDate(date) && isValidCheckout(date);

  // A free day that an active promotion covers. Takes the violet tint
  // instead of the plain green one, so an offer is visible in the calendar
  // before the guest has picked anything.
  const isPromotedDate = (date: Date) =>
    promotionsForDate(promotions, format(date, "yyyy-MM-dd")).length > 0;

  // Only the days strictly *between* the two ends — react-day-picker's
  // `range_middle`, whose accent fill an `!important` Tailwind background
  // would paint over. The ends themselves, and a lone check-in, stay in their
  // day category: react-day-picker leaves their cell either unpainted or
  // half-transparent, so the category fill shows around the accent circle and
  // the selection sits in the same block of colour as the days beside it.
  const isRangeMiddleDate = (date: Date) =>
    (!!range?.from && !!range?.to && isAfter(date, range.from) && isBefore(date, range.to)) ||
    (!!range?.from && !range?.to && !!hoverDate && hoverIsValidCheckout &&
      isAfter(date, range.from) && isBefore(date, hoverDate));

  // Every day the selection has claimed — the two ends and everything between
  // them, or the check-in and the checkout currently being hovered. Their
  // cells are decoration around a fixed accent circle, so they keep their
  // category fill but drop its `hover:` variant: without that the day under
  // the pointer lifts to a brighter tint than the identical cell at the other
  // end of the bar, which reads as a mismatch rather than as feedback.
  const isSelectionDate = (date: Date) =>
    isRangeMiddleDate(date) ||
    (!!range?.from && isSameDay(date, range.from)) ||
    (!!range?.to && isSameDay(date, range.to)) ||
    (!!range?.from && !range?.to && !!hoverDate && hoverIsValidCheckout &&
      isSameDay(date, hoverDate));

  // The three day categories that carry a `hover:` variant, hoisted so each
  // can drive both its fill modifier and its hover-only twin.
  const isPromotedCell = (date: Date) =>
    !isRangeMiddleDate(date) &&
    !isPastDate(date) &&
    !isOccupiedDate(date) &&
    !isInvalidCheckoutCandidate(date) &&
    isPromotedDate(date);

  const isAvailableCell = (date: Date) =>
    !isRangeMiddleDate(date) &&
    !isPastDate(date) &&
    !isBookedDate(date) &&
    !hasNoPrice(date) &&
    !isInvalidCheckoutCandidate(date) &&
    !isPromotedDate(date);

  const isOccupiedCheckoutCell = (date: Date) =>
    !isRangeMiddleDate(date) && isOccupiedValidCheckout(date);

  // react-day-picker has no tooltip API, and a native `title` attribute has
  // a ~1s delay and no styling, so the day button is rendered ourselves.
  // Memoized on exactly what its output depends on: without that, a new
  // component identity on every render (hover included) would remount every
  // button in the grid and steal keyboard focus mid-navigation.
  const DayButtonWithPromotions = useMemo(
    () => makePromotionDayButton(promotions, dict, currency),
    [promotions, dict, currency]
  );

  // Embedded (not portaled) — a plain conditionally-mounted block, in flow
  // right below the date fields. Its appearing/disappearing (both size and
  // reveal) is animated entirely by the widget-resize FLIP effect above,
  // which measures this element's natural size once mounted; giving it its
  // own separate transition here would fight that effect's forced reflow
  // and desync the two animations. Stays mounted through calendarMounted
  // (not calendarOpen directly) so it's still present — and visibly clipped
  // by the shrinking box — for the whole closing animation.
  const dateAndGuestCalendar = calendarMounted && (
    <div ref={calendarRef}>
      <div className="pt-4 w-max max-w-full mx-auto overflow-x-auto">
        <DayPicker
          mode="range"
          navLayout="around"
          style={{
            "--rdp-months-gap": "1.5rem",
          } as React.CSSProperties}
          styles={{ months: { flexWrap: "nowrap" } }}
          selected={range}
          defaultMonth={range?.from ?? today}
          onSelect={(newRange, triggerDate) => {
            // While picking a checkout date, validate the clicked day directly
            // against the original check-in rather than trusting react-day-picker's
            // computed range: its own range logic silently swaps check-in to
            // the clicked date whenever the naive selection would cross an
            // occupied date, which would otherwise look like check-in moved.
            if (range?.from && !range?.to) {
              // A day before the pending check-in restarts the selection from
              // that day instead of becoming a backwards range: react-day-picker
              // would turn it into { from: clicked, to: previous check-in },
              // which completes a stay that was never checked against the
              // minimum stay of its own check-in date.
              if (isBefore(triggerDate, range.from)) {
                setRange({ from: triggerDate, to: undefined });
                return;
              }
              if (isAfter(triggerDate, range.from)) {
                if (isValidCheckout(triggerDate)) setRange({ from: range.from, to: triggerDate });
                return;
              }
              // Re-clicking the check-in itself falls through, clearing the selection.
            }
            setRange(newRange);
          }}
          onDayClick={(date, modifiers) => {
            if (modifiers.disabled) return;
            // Both dates were already picked; start a fresh selection instead of adjusting the old range
            if (range?.from && range?.to) {
              setRange({ from: date, to: undefined });
            }
          }}
          numberOfMonths={2}
          disabled={(date) => {
            if (isPastDate(date)) return true;
            if (hasNoPrice(date)) return true;
            if (isBookedDate(date)) return !isOccupiedValidCheckout(date);
            return false;
          }}
          excludeDisabled
          showOutsideDays={false}
          locale={dateFnsLocale}
          min={1}
          onDayMouseEnter={(date) => setHoverDate(date)}
          onDayMouseLeave={() => setHoverDate(undefined)}
          components={{ DayButton: DayButtonWithPromotions }}
          modifiers={{
            hoverRange: (date) =>
              !!range?.from &&
              !range?.to &&
              !!hoverDate &&
              hoverIsValidCheckout &&
              isAfter(date, range.from) &&
              isBefore(date, hoverDate),
            hoverRangeEnd: (date) =>
              !!range?.from &&
              !range?.to &&
              !!hoverDate &&
              hoverIsValidCheckout &&
              isSameDay(date, hoverDate),
            // The check-in itself while a checkout is being hovered. Without
            // it the preview bar starts only at the *next* cell's edge, so it
            // stops a cell-half short of the check-in circle — a gap the
            // finished range never has, since react-day-picker fills the
            // inner half of its own `range_start`.
            hoverRangeStart: (date) =>
              !!range?.from &&
              !range?.to &&
              !!hoverDate &&
              hoverIsValidCheckout &&
              isAfter(hoverDate, range.from) &&
              isSameDay(date, range.from),
            // Listed before `available` so a promoted free day takes the
            // promotion tint rather than the green one.
            promoted: isPromotedCell,
            promotedHover: (date) => isPromotedCell(date) && !isSelectionDate(date),
            available: isAvailableCell,
            availableHover: (date) => isAvailableCell(date) && !isSelectionDate(date),
            past: (date) => !isRangeMiddleDate(date) && isPastDate(date),
            occupiedCheckout: isOccupiedCheckoutCell,
            occupiedCheckoutHover: (date) =>
              isOccupiedCheckoutCell(date) && !isSelectionDate(date),
            unavailable: (date) =>
              !isRangeMiddleDate(date) &&
              !isPastDate(date) &&
              !isOccupiedValidCheckout(date) &&
              (isBookedDate(date) || hasNoPrice(date) || isInvalidCheckoutCandidate(date)),
          }}
          modifiersClassNames={{
            hoverRange: "rdp-range_middle",
            hoverRangeEnd: "rdp-range_end",
            hoverRangeStart: "rdp-range_start",
            // A brighter, more saturated green than `available`: on dark
            // the two sat a hair apart (green-950/40 vs /50) and read as
            // the same block, so promoted jumps up to green-700/45.
            promoted:
              "!bg-green-100 dark:!bg-green-700/45 !text-green-800 dark:!text-green-100 " +
              "!font-semibold",
            promotedHover: "hover:!bg-green-200 dark:hover:!bg-green-600/55",
            available: "!bg-green-50 dark:!bg-green-950/40 !text-green-800 dark:!text-green-300",
            availableHover: "hover:!bg-green-100 dark:hover:!bg-green-900/40",
            past: "!bg-gray-100 dark:!bg-gray-800/60 !text-gray-400 dark:!text-gray-600",
            occupiedCheckout: "!bg-yellow-50 dark:!bg-yellow-950/40 !text-yellow-800 dark:!text-yellow-400",
            occupiedCheckoutHover: "hover:!bg-yellow-100 dark:hover:!bg-yellow-900/40",
            unavailable: "!bg-red-50 dark:!bg-red-950/40 !text-red-700 dark:!text-red-400",
          }}
        />
      </div>
    </div>
  );

  /* ── Checkin / checkout / adults / children, display-only summary
     shown across every step of the extended (post rate-selection) flow ── */
  const bookingDataSummary = range?.from && (
    <div className="flex flex-nowrap items-start gap-3 overflow-x-auto pb-0.5">
      <div className="flex items-start gap-2 shrink-0">
        <StaticField label={dict.checkIn} value={checkInText} />
        <div className="flex flex-col items-center shrink-0">
          <span className="invisible text-xs">&nbsp;</span>
          <span className="text-gray-300 dark:text-gray-600 text-lg leading-5 select-none">→</span>
        </div>
        <StaticField label={dict.checkOut} value={checkOutText} />
      </div>

      <StaticField className="ml-6 sm:ml-8" label={dict.adults} value={String(adults)} />
      <StaticField label={dict.children} value={String(children.length)} />
    </div>
  );

  // Action row for whichever step is showing, rendered outside the
  // scrollable content area (below) so it stays put — visible and
  // reachable — regardless of how tall that step's content gets. The
  // "payment" step is the one exception: its Pay/Verify button lives
  // inside PaymentStep's own Stripe <Elements> tree and can't be hoisted
  // out here, so it pins its own action row within the scrollable area.
  const footer = !extended ? (
    <>
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

      <p className="text-center text-xs text-gray-400 dark:text-gray-500 mt-3">
        {dict.noCharge}
      </p>
    </>
  ) : guestStep === "plan" && verified && range?.from ? (
    <div className="flex gap-3">
      <button
        type="button"
        onClick={cancelBookingFlow}
        className="flex-1 text-gray-600 dark:text-gray-300 font-semibold py-4 rounded-xl text-base transition-all border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 active:scale-[0.98] cursor-pointer"
      >
        {dict.cancel}
      </button>
      <button
        type="button"
        disabled={!selectedPlan}
        onClick={() => setGuestStep("form")}
        className="flex-1 text-white font-semibold py-4 rounded-xl text-base transition-all shadow-lg active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
      >
        {dict.modal.next}
      </button>
    </div>
  ) : guestStep === "form" && guestForm && verified ? (
    <>
      <div className="flex gap-3">
        <button
          type="button"
          onClick={() => setGuestStep("plan")}
          className="flex-1 text-gray-600 dark:text-gray-300 font-semibold py-4 rounded-xl text-base transition-all border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 active:scale-[0.98] cursor-pointer"
        >
          {dict.back}
        </button>
        <button
          type="button"
          onClick={handleGuestFormSubmit}
          disabled={pending || !isFormValid || !isGuestDetailsValid}
          className="flex-1 text-white font-semibold py-4 rounded-xl text-base transition-all shadow-lg active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
        >
          {dict.modal.next}
        </button>
      </div>
      <button
        type="button"
        onClick={cancelBookingFlow}
        className="block w-full text-center text-xs text-gray-400 dark:text-gray-500 hover:text-teal-700 dark:hover:text-teal-400 cursor-pointer mt-3"
      >
        {dict.cancel}
      </button>
    </>
  ) : guestStep === "success" || guestStep === "pending" ? (
    <button
      type="button"
      onClick={handleDone}
      className="w-full text-white font-semibold py-3 rounded-xl text-sm transition-all shadow-lg cursor-pointer"
      style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
    >
      {dict.modal.done}
    </button>
  ) : guestStep === "conflict" ? (
    // handleDone, never cancelBookingFlow: the booking this flow was for is
    // already gone server-side, so there is nothing left to delete — and it
    // clears the dead date range, which is the whole point of the button.
    <button
      type="button"
      onClick={handleDone}
      className="w-full text-white font-semibold py-3 rounded-xl text-sm transition-all shadow-lg cursor-pointer"
      style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
    >
      {dict.modal.chooseNewDates}
    </button>
  ) : guestStep === "error" ? (
    <>
      <button
        type="button"
        onClick={() => setGuestStep("form")}
        className="w-full text-white font-semibold py-3 rounded-xl text-sm transition-all shadow-lg cursor-pointer"
        style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
      >
        {dict.modal.tryAgain}
      </button>
      <button
        type="button"
        onClick={cancelBookingFlow}
        className="block w-full text-center text-xs text-gray-400 dark:text-gray-500 hover:text-teal-700 dark:hover:text-teal-400 cursor-pointer mt-3"
      >
        {dict.cancel}
      </button>
    </>
  ) : null;

  return (
    <>
      {/* Only a desktop concept — on mobile extended mode is inline page
          content, not an overlay, so there's nothing to dim behind it. */}
      <div
        className={`fixed inset-0 z-[90] bg-black/40 transition-opacity ease-in-out opacity-0 pointer-events-none ${
          extended ? "lg:opacity-100 lg:pointer-events-auto" : ""
        }`}
        style={{ transitionDuration: `${TRANSITION_MS}ms` }}
      />
      <div
        ref={widgetRef}
        className={`bg-white dark:bg-gray-800 rounded-2xl shadow-2xl flex flex-col ${
          extended
            ? // Mobile (base): a plain in-flow block, full window width via the
              // classic "full-bleed" trick (relative + left-1/2 + negative
              // translate breaks it out of the hero section's side padding),
              // no independent scrolling — it grows/shrinks with the page.
              // Desktop (lg:): unchanged floating, centered overlay. Only the
              // middle content area scrolls (below) — the header and the
              // step's action row stay fixed in place, out of that scroll.
              "relative w-screen left-1/2 -translate-x-1/2 lg:fixed lg:z-[91] lg:w-full lg:max-w-3xl lg:max-h-[90vh] lg:overflow-hidden"
            : calendarOpen
            ? "absolute z-[91] max-w-[min(680px,calc(100vw-1.5rem))] max-lg:left-1/2 max-lg:-translate-x-1/2"
            : "w-full"
        }`}
        style={{ top: pinnedTop ?? undefined, right: pinnedRight ?? undefined }}
      >
        {/* ── Header ────────────────────────────────────────── */}
        <div
          className="relative px-6 py-5 rounded-t-2xl shrink-0"
          style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
        >
          {/* Wrapping, not nowrap: the title and the price group only share a
              line when they actually fit on one. The compact widget is a
              narrow sidebar card, and a promotion adds a struck-through
              regular price to the price group — held on one rigid row, that
              pair overflowed the header and spilled onto the card below it. */}
          <div className="flex flex-col gap-1 lg:flex-row lg:flex-wrap lg:items-baseline lg:justify-between lg:gap-x-4 lg:gap-y-1">
            <div className="flex flex-col gap-0.5 min-w-0">
              <h2 className="text-lg lg:text-xl font-bold text-white [text-shadow:0_1px_3px_rgba(0,0,0,0.35)]">{headerTitle}</h2>
              {nights > 0 && (
                <p className="text-white/85 text-sm [text-shadow:0_1px_2px_rgba(0,0,0,0.35)]">
                  {nights} {nights !== 1 ? dict.nights : dict.night} · {totalGuests}{" "}
                  {totalGuests !== 1 ? dict.guests : dict.guest}
                </p>
              )}
            </div>
            {/* Figure column then unit column: the two price lines are cells
                of one grid, so the euro figure and its CHF companion share a
                right edge and both units start at the same x — which neither
                gets from being two independently laid out lines, since the
                lines are set at different sizes and only one carries the
                "from" prefix. */}
            <div
              className="shrink-0 grid grid-cols-[auto_auto] items-baseline gap-x-1 justify-start lg:justify-end"
              hidden={!showHeaderPrice}
            >
              <div className="text-right whitespace-nowrap">
                {showFromPrefix && (
                  <span className="text-white/90 text-base mr-1 [text-shadow:0_1px_2px_rgba(0,0,0,0.35)]">{dict.fromPrefix}</span>
                )}
                <span
                  // justify-end: any slack in the reserved slot (a three-digit
                  // price in room kept for four) falls before the figure, so
                  // the figure stays tight against its column's right edge and
                  // the two header lines' figures line up under each other.
                  className="inline-flex items-baseline justify-end text-lg lg:text-xl font-bold text-white [text-shadow:0_1px_3px_rgba(0,0,0,0.35)]"
                  style={{ minWidth: priceSlot(currency) }}
                >
                  {headerPrice !== null && headerRegularPrice !== null ? (
                    <PriceWithDiscount
                      price={headerPrice}
                      regularPrice={headerRegularPrice}
                      currency={currency}
                      regularClassName="!text-white/70"
                    />
                  ) : (
                    <PricePlaceholder width={priceSlot(currency)} />
                  )}
                </span>
              </div>
              {/* Rendered while loading too: the unit never depends on a
                  price having arrived, and dropping it would resize the
                  header the moment one does. */}
              <span className="text-white/90 text-base whitespace-nowrap [text-shadow:0_1px_2px_rgba(0,0,0,0.35)]">
                {nights > 0 ? dict.total : dict.perNight}
              </span>
              {/* The CHF companion line is decided by the currency alone, not
                  by whether its figure is in hand — the two prices always
                  arrive together, so holding this row open (with a
                  placeholder in it) is what keeps the header one fixed
                  height from first paint through to the loaded prices. */}
              {currency !== "CHF" && (
                <>
                  <div className="text-right text-white/85 text-sm [text-shadow:0_1px_2px_rgba(0,0,0,0.35)]">
                    <span className="inline-flex items-baseline justify-end" style={{ minWidth: priceSlot("CHF") }}>
                      {headerPriceChf !== null && headerRegularPriceChf !== null ? (
                        <PriceWithDiscount
                          price={headerPriceChf}
                          regularPrice={headerRegularPriceChf}
                          currency="CHF"
                          className="font-normal"
                          regularClassName="!text-white/60"
                        />
                      ) : (
                        <PricePlaceholder width={priceSlot("CHF")} />
                      )}
                    </span>
                  </div>
                  <span className="text-white/85 text-sm whitespace-nowrap [text-shadow:0_1px_2px_rgba(0,0,0,0.35)]">
                    {nights > 0 ? dict.total : dict.perNight}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>

        <div className="p-6 pb-0 lg:overflow-y-auto lg:flex-1 lg:min-h-0">
          {!extended ? (
            <>
              {/* ── Date inputs + dropdown calendar ───────────────── */}
              <section ref={dateRef} className="relative mb-5">
                <h3 className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest mb-3">
                  {dict.selectDates}
                </h3>

                <div className="flex items-end gap-2">
                  <DateField
                    label={dict.checkIn}
                    value={checkInText}
                    onClick={toggleCalendar}
                    active={calendarOpen}
                    filled={!!range?.from}
                    openCalendarLabel={dict.openCalendar}
                  />
                  <span className="pb-[11px] text-gray-300 dark:text-gray-600 text-lg select-none">→</span>
                  <DateField
                    label={dict.checkOut}
                    value={checkOutText}
                    onClick={toggleCalendar}
                    active={calendarOpen}
                    filled={!!range?.to}
                    openCalendarLabel={dict.openCalendar}
                  />
                </div>

                {dateAndGuestCalendar}
              </section>

              <div className="border-t border-gray-100 dark:border-gray-700 my-4" />

              {/* ── Guests ────────────────────────────────────────── */}
              <section className="mb-5">
                <h3 className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest mb-3">
                  {dict.guestsSection}
                </h3>

                <div className="flex items-center justify-between py-3 border-b border-gray-100 dark:border-gray-700">
                  <div>
                    <p className="font-medium text-gray-800 dark:text-gray-200 text-sm">{dict.adults}</p>
                    <p className="text-xs text-gray-400 dark:text-gray-500">{dict.adultsAge}</p>
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
                    <p className="font-medium text-gray-800 dark:text-gray-200 text-sm">{dict.children}</p>
                    <p className="text-xs text-gray-400 dark:text-gray-500">{dict.childrenAge}</p>
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
            </>
          ) : (
            <>
              {bookingDataSummary && (
                <>
                  {bookingDataSummary}
                  <div className="border-t border-gray-100 dark:border-gray-700 my-5" />
                </>
              )}

              {guestStep === "plan" && verified && range?.from && (
                <div className="space-y-5">
                  <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
                    {dict.modal.choosePlanTitle}
                  </h3>

                  {plans.length === 0 ? (
                    <p className="text-sm text-gray-600 dark:text-gray-300">{dict.modal.noPlan}</p>
                  ) : (
                    <div className="space-y-2">
                      {visiblePlans.map((p) => {
                        // Straight from the server's quote for this plan —
                        // discounted total, undiscounted total, and the
                        // per-night figures — with nothing computed here.
                        const planQuote = planQuoteFor(p._id);
                        const activePlanPrice = planQuote
                          ? nights > 0
                            ? planQuote.price
                            : planQuote.price_per_night
                          : null;
                        const activePlanRegularPrice = planQuote
                          ? nights > 0
                            ? planQuote.regular_price
                            : planQuote.regular_price_per_night
                          : null;
                        const isSelected = selectedPlanId === p._id;
                        const highlight = refundHighlightColor(p.cancellation_policy.rules, range.from!, today);
                        const highlightBackground = `rgba(${highlight[0]}, ${highlight[1]}, ${highlight[2]}, ${isSelected ? 0.3 : 0.14})`;
                        return (
                          <button
                            key={p._id}
                            type="button"
                            onClick={() => setSelectedPlanId(p._id)}
                            style={{ backgroundColor: highlightBackground }}
                            className={`w-full text-left p-3 rounded-xl transition-colors cursor-pointer ${
                              isSelected
                                ? "border-[3px] border-teal-600 dark:border-teal-400"
                                : "border-2 border-gray-200 dark:border-gray-600 hover:border-teal-300 dark:hover:border-teal-700"
                            }`}
                          >
                            <div className="flex items-start gap-3">
                              <span
                                aria-hidden="true"
                                className={`mt-1 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 transition-colors ${
                                  isSelected
                                    ? "border-teal-600 dark:border-teal-400"
                                    : "border-gray-300 dark:border-gray-500"
                                }`}
                              >
                                {isSelected && (
                                  <span className="h-2.5 w-2.5 rounded-full bg-teal-600 dark:bg-teal-400" />
                                )}
                              </span>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-baseline justify-between gap-3">
                                  <span className="inline-flex items-baseline text-2xl font-bold text-gray-800 dark:text-gray-100">
                                    {activePlanPrice !== null && activePlanRegularPrice !== null ? (
                                      <PriceWithDiscount
                                        price={activePlanPrice}
                                        regularPrice={activePlanRegularPrice}
                                        currency={currency}
                                      />
                                    ) : (
                                      <LoadingSpinner className="w-5 h-5 self-center" />
                                    )}
                                  </span>
                                  {nights > 0 && activePlanPrice !== null && (
                                    <span className="text-sm text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                                      {dict.total}
                                    </span>
                                  )}
                                </div>
                                {nights > 0 && planQuote !== null && (
                                  <p className="inline-flex items-baseline text-base text-gray-500 dark:text-gray-400 mt-0.5">
                                    <PriceWithDiscount
                                      price={planQuote.price_per_night}
                                      regularPrice={planQuote.regular_price_per_night}
                                      currency={currency}
                                      className="font-normal"
                                    />
                                    {dict.perNight}
                                  </p>
                                )}
                                {activePlanPrice !== null && (
                                  <CancellationTimeline
                                    rules={p.cancellation_policy.rules}
                                    checkInDate={range.from!}
                                    today={today}
                                    dateLocale={dateFnsLocale}
                                    price={activePlanPrice}
                                    currency={currency}
                                    cancellationLabel={dict.modal.cancellationLabel}
                                    tillTemplate={dict.modal.cancellationTill}
                                    rangeTemplate={dict.modal.cancellationRange}
                                    freeLabel={dict.modal.cancellationFree}
                                    chargeTemplate={dict.modal.cancellationCharge}
                                  />
                                )}
                              </div>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {guestStep === "form" && guestForm && verified && (
                <div className="space-y-5">
                  {childAgesBlock}

                  {/* ── Guest details ─────────────────────────────── */}
                  <h3 className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest">
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
                    <PhoneInput
                      tone="booking"
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
                    <CountrySelect
                      label={dict.modal.country}
                      value={guestForm.residence_address.country}
                      noneLabel={dict.modal.selectCountry}
                      noMatchesLabel={dict.modal.noMatchesCountry}
                      locale={lang}
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

                  {formError && <p className="text-sm text-red-600 dark:text-red-400">{formError}</p>}
                </div>
              )}

              {guestStep === "submitting" && (
                <p className="text-sm text-gray-600 dark:text-gray-300 text-center py-8">{dict.modal.submitting}</p>
              )}

              {guestStep === "payment" && paymentIntent && guestForm && (
                <PaymentStep
                  intent={paymentIntent}
                  dict={dict.modal.payment}
                  lang={lang}
                  guestName={`${guestForm.first_name} ${guestForm.family_name}`.trim()}
                  guestEmail={guestForm.email}
                  onSuccess={awaitPaymentOutcome}
                  onBack={() => setGuestStep("form")}
                  backLabel={dict.back}
                  onCancel={cancelBookingFlow}
                  cancelLabel={dict.cancel}
                />
              )}

              {guestStep === "confirming" && (
                <div className="text-center py-8 space-y-3">
                  <div
                    className="mx-auto h-6 w-6 rounded-full border-2 border-gray-200 dark:border-gray-600 border-t-teal-600 dark:border-t-teal-400 animate-spin"
                    role="status"
                    aria-label={dict.modal.confirmingTitle}
                  />
                  <p className="text-sm text-gray-600 dark:text-gray-300">{dict.modal.confirmingMessage}</p>
                </div>
              )}

              {guestStep === "success" && (
                <div className="text-center py-4 space-y-2">
                  <p className="text-sm text-gray-700 dark:text-gray-300">
                    {dict.modal.successMessage.replace("{name}", guestForm?.first_name ?? "")}
                  </p>
                  <p className="text-sm text-gray-500 dark:text-gray-400">{dict.modal.emailNotice}</p>
                </div>
              )}

              {/* The dates went to whoever paid first. Deliberately spells
                  out all three things the guest needs: that there is no
                  booking, which nights were lost, and that they are not out
                  of pocket for it. */}
              {guestStep === "conflict" && (
                <div className="text-center py-4 space-y-2">
                  <p className="text-sm text-gray-700 dark:text-gray-300">
                    {dict.modal.conflictMessage.replace(
                      "{dates}",
                      dict.modal.cancellationRange
                        .replace("{startDate}", checkInText)
                        .replace("{endDate}", checkOutText)
                    )}
                  </p>
                  <p className="text-sm text-gray-500 dark:text-gray-400">{dict.modal.conflictRefundNotice}</p>
                </div>
              )}

              {guestStep === "pending" && (
                <div className="text-center py-4 space-y-2">
                  <p className="text-sm text-gray-700 dark:text-gray-300">{dict.modal.pendingMessage}</p>
                </div>
              )}

              {guestStep === "error" && (
                <div className="text-center py-4">
                  <p className="text-sm text-red-600 dark:text-red-400">{formError}</p>
                </div>
              )}
            </>
          )}
        </div>

        {footer && (
          <div
            className={
              extended
                ? "px-6 pb-6 pt-4 border-t border-gray-100 dark:border-gray-700 shrink-0"
                : "px-6 pb-6 shrink-0"
            }
          >
            {footer}
          </div>
        )}
      </div>
      <div ref={spacerRef} aria-hidden="true" style={{ height: 0 }} />

      {identityModalOpen && (
        <BookingModal
          dict={dict.modal}
          lang={lang}
          currency={currency}
          onClose={() => setIdentityModalOpen(false)}
          onVerified={handleVerified}
        />
      )}
    </>
  );
}

/* ── Promotion tooltip ─────────────────────────────────── */

/** The tooltip line for one promotion, split so the offer's name can be
 *  emphasised while the wording itself stays in the dictionaries. */
function promotionTooltipParts(
  promotion: PublicPromotion,
  dict: BookingDict,
  currency: Currency
): { before: string; name: string; after: string } {
  const template =
    promotion.discount_type === "percent"
      ? dict.promotionPercentTooltip.replace("{percent}", String(Math.round(promotion.discount_ratio * 100)))
      : dict.promotionAmountTooltip.replace("{amount}", formatPrice(promotion.discount_amount, currency));
  const [before, after = ""] = template
    .replace("{nights}", String(promotion.min_stay_days))
    .split("{name}");
  return { before, name: promotion.name, after };
}

/**
 * Builds the calendar's day button: the default button, plus a tooltip for
 * whichever promotions cover that day.
 *
 * A factory rather than a plain component because react-day-picker only
 * hands the component `day` and `modifiers` — the promotions, wording and
 * currency have to be closed over. The caller memoizes the result so the
 * grid isn't remounted on every render.
 *
 * The same text rides along as an `aria-label` so screen readers get the
 * offer too, and as a `title` while the tooltip is up so the two never
 * disagree.
 *
 * Visibility is driven by pointer state rather than `:hover`/`:focus-within`:
 * a click has to dismiss the tooltip (it otherwise sat over the calendar for
 * as long as the day kept focus), and it may only come back once the pointer
 * has actually left the day and come back.
 *
 * The tooltip itself is portaled to `document.body` and positioned `fixed`
 * against the day's own rect: the calendar sits in two scroll boxes (the
 * grid's `overflow-x-auto` and the widget's `lg:overflow-y-auto`), which
 * would otherwise clip a tooltip reaching past a day at the edge — or, worse,
 * count it as content and grow a scrollbar around it. Positioned in the
 * window, it can flip below the day when there's no room above it and be
 * clamped to the window's sides, and it needs no room inside the widget at
 * all.
 */
function makePromotionDayButton(
  promotions: PublicPromotion[],
  dict: BookingDict,
  currency: Currency
) {
  return function PromotionDayButton({ day, modifiers, ...buttonProps }: DayButtonProps) {
    // "hidden" until the pointer arrives, "shown" while it is over the day,
    // and "dismissed" from a click until the pointer leaves again.
    const [tooltipState, setTooltipState] = useState<"hidden" | "shown" | "dismissed">("hidden");
    // Window coordinates for the portaled tooltip, measured once it is in the
    // DOM. Null means "not placed yet", which renders it invisible rather
    // than in the top-left corner for a frame.
    const [tooltipPos, setTooltipPos] = useState<{ top: number; left: number } | null>(null);
    const anchorRef = useRef<HTMLSpanElement>(null);
    const tooltipRef = useRef<HTMLSpanElement>(null);
    const tooltipVisible = tooltipState === "shown";

    // Placed in a layout effect (before paint, so there's no visible jump)
    // and kept in place while it is up: the page, the widget's own scroll box
    // and the calendar's horizontal one can all move the day out from under
    // a fixed tooltip, and `capture` is what picks up those inner scrolls.
    useLayoutEffect(() => {
      if (!tooltipVisible) {
        setTooltipPos(null);
        return;
      }
      const place = () => {
        const anchor = anchorRef.current?.getBoundingClientRect();
        const tooltip = tooltipRef.current?.getBoundingClientRect();
        if (!anchor || !tooltip) return;
        const above = anchor.top - tooltip.height - TOOLTIP_GAP;
        setTooltipPos({
          // Below the day when the window has no room above it.
          top: above >= TOOLTIP_MARGIN ? above : anchor.bottom + TOOLTIP_GAP,
          left: Math.min(
            Math.max(anchor.left + anchor.width / 2 - tooltip.width / 2, TOOLTIP_MARGIN),
            window.innerWidth - tooltip.width - TOOLTIP_MARGIN
          ),
        });
      };
      place();
      window.addEventListener("scroll", place, true);
      window.addEventListener("resize", place);
      return () => {
        window.removeEventListener("scroll", place, true);
        window.removeEventListener("resize", place);
      };
    }, [tooltipVisible]);

    const dayPromotions = promotionsForDate(promotions, format(day.date, "yyyy-MM-dd"));
    if (dayPromotions.length === 0 || modifiers.disabled) {
      return <button {...buttonProps} />;
    }

    const lines = dayPromotions.map((promotion) => ({
      promotion,
      parts: promotionTooltipParts(promotion, dict, currency),
    }));
    const plainText = lines
      .map(({ parts }) => `${parts.before}${parts.name}${parts.after}`)
      .join(" · ");

    return (
      <span
        ref={anchorRef}
        className="block"
        onPointerEnter={(event) => {
          // Touch taps fire enter/leave around the click, which would flash
          // the tooltip open; only a real pointer opens it.
          if (event.pointerType === "mouse") setTooltipState("shown");
        }}
        onPointerLeave={() => setTooltipState("hidden")}
      >
        <button
          {...buttonProps}
          title={tooltipVisible ? plainText : undefined}
          aria-label={`${buttonProps["aria-label"] ?? ""} ${plainText}`.trim()}
          onClick={(event) => {
            setTooltipState("dismissed");
            buttonProps.onClick?.(event);
          }}
        />
        {tooltipVisible &&
          createPortal(
            <span
              ref={tooltipRef}
              role="tooltip"
              className="pointer-events-none fixed z-[200] w-max rounded-lg bg-gray-900 dark:bg-gray-700 px-2.5 py-1.5 text-left text-xs font-normal leading-snug text-white shadow-xl"
              style={{
                top: tooltipPos?.top ?? 0,
                left: tooltipPos?.left ?? 0,
                // Never wider than the window it is clamped inside, so the
                // clamp can always find a spot for it.
                maxWidth: `min(15rem, calc(100vw - ${TOOLTIP_MARGIN * 2}px))`,
                visibility: tooltipPos ? "visible" : "hidden",
              }}
            >
              <span className="block font-semibold text-violet-200">{dict.specialOffer}</span>
              {lines.map(({ promotion, parts }) => (
                <span key={promotion._id} className="block">
                  {parts.before}
                  <strong className="font-semibold">{parts.name}</strong>
                  {parts.after}
                </span>
              ))}
            </span>,
            document.body
          )}
      </span>
    );
  };
}

/* ── DateField ─────────────────────────────────────────── */
function DateField({
  label,
  value,
  onClick,
  active,
  filled,
  openCalendarLabel,
}: {
  label: string;
  value: string;
  onClick: () => void;
  active: boolean;
  filled: boolean;
  openCalendarLabel: string;
}) {
  return (
    <div className="flex-1 min-w-0">
      <label className="block text-xs font-medium text-gray-400 dark:text-gray-500 mb-1">{label}</label>
      <button
        type="button"
        onClick={onClick}
        aria-label={openCalendarLabel}
        className={`relative w-full pl-3 pr-9 py-2.5 rounded-xl border text-sm text-left transition-colors cursor-pointer focus:outline-none focus:ring-1 ${
          filled
            ? "border-teal-400 dark:border-teal-600 bg-teal-50 dark:bg-teal-950/30 text-gray-800 dark:text-gray-100 focus:border-teal-500 focus:ring-teal-200"
            : active
            ? "border-teal-400 dark:border-teal-600 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 focus:border-teal-500 focus:ring-teal-200"
            : "border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:border-teal-400 focus:ring-teal-100"
        }`}
      >
        <span className={value ? "" : "text-gray-300 dark:text-gray-500"}>
          {value || DATE_PLACEHOLDER}
        </span>
        <span
          className={`absolute right-2.5 top-1/2 -translate-y-1/2 transition-colors ${
            active ? "text-teal-600 dark:text-teal-400" : "text-gray-400 dark:text-gray-500"
          }`}
        >
          <CalendarIcon />
        </span>
      </button>
    </div>
  );
}

/* ── StaticField (plain-text display value, not interactive) ── */
function StaticField({
  label,
  value,
  className = "",
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div className={`shrink-0 ${className}`}>
      <p className="text-xs font-medium text-gray-400 dark:text-gray-500 whitespace-nowrap">{label}</p>
      <p className="text-sm font-medium text-gray-800 dark:text-gray-100 whitespace-nowrap">{value}</p>
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

/* ── PricePlaceholder ──────────────────────────────────── */
/**
 * A shimmering bar standing in for a header price still being fetched.
 *
 * Unlike a spinner it occupies the text's own line box: the non-breaking
 * space sets the height from the surrounding font size and line height, and
 * the bar itself is taken out of flow on top of it. Given the same `width`
 * its slot reserves (see PRICE_SLOT_CH), a price appearing changes neither
 * the header's height nor the position of the text around the figure.
 */
function PricePlaceholder({ width }: { width: string }) {
  return (
    <span className="relative inline-block align-baseline" style={{ width }} role="status" aria-label="Loading price">
      &nbsp;
      <span className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-[0.66em] rounded bg-white/30 animate-pulse" />
    </span>
  );
}

/* ── LoadingSpinner ────────────────────────────────────── */
function LoadingSpinner({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" role="status" aria-label="Loading price">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
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
        type="button"
        onClick={onDecrement}
        disabled={value <= min}
        className="w-8 h-8 rounded-full border-2 border-gray-300 dark:border-gray-600 flex items-center justify-center text-gray-600 dark:text-gray-300 font-medium hover:border-teal-500 hover:text-teal-600 dark:hover:text-teal-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
      >
        −
      </button>
      <span className="w-5 text-center font-semibold text-gray-800 dark:text-gray-100 text-sm">{value}</span>
      <button
        type="button"
        onClick={onIncrement}
        disabled={value >= max}
        className="w-8 h-8 rounded-full border-2 border-gray-300 dark:border-gray-600 flex items-center justify-center text-gray-600 dark:text-gray-300 font-medium hover:border-teal-500 hover:text-teal-600 dark:hover:text-teal-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
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
      <label htmlFor={id} className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
        {label}
      </label>
      <input
        id={id}
        type={type}
        required={required}
        disabled={disabled}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-teal-300 focus:border-teal-400 disabled:bg-gray-50 dark:disabled:bg-gray-700 disabled:text-gray-400"
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
  required = false,
}: {
  label: string;
  value: string;
  options: string[];
  noneLabel: string;
  onChange: (v: string) => void;
  required?: boolean;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
        {label}
      </label>
      <select
        id={id}
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-600 text-sm bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-teal-300 focus:border-teal-400 cursor-pointer"
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
