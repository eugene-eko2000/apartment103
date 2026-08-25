"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { format, differenceInCalendarDays, parse, parseISO } from "date-fns";
import { enUS, de, fr, it } from "date-fns/locale";
import type { Locale as DateFnsLocale } from "date-fns";
import { ApiError, type Booking, type BookingCharge, type BookingDisplay } from "@/lib/api";
import { formatPrice } from "@/lib/currency-config";
import { useCurrency } from "@/lib/currency-context";
import { applicableRefundPercentage } from "@/lib/refund";
import { CancellationTimeline, fillForRefund } from "@/components/CancellationTimeline";
import PriceWithDiscount from "@/components/PriceWithDiscount";
import type { Locale } from "@/lib/i18n-config";

const DATE_FNS_LOCALES: Record<Locale, DateFnsLocale> = { en: enUS, de, fr, it };

export interface BookingDetailsDict {
  close: string;
  title: string;
  checkIn: string;
  checkOut: string;
  night: string;
  nights: string;
  averageNightly: string;
  priceBreakdown: string;
  totalPrice: string;
  cancellationPolicy: string;
  cancellationLabel: string;
  cancellationTill: string;
  cancellationRange: string;
  cancellationFree: string;
  cancellationCharge: string;
  paymentInfo: string;
  paidSection: string;
  upcomingSection: string;
  noPayments: string;
  noUpcomingCharges: string;
  chargeReasonInitial: string;
  chargeReasonAccrual: string;
  chargeReasonSettlement: string;
  cancelledStatus: string;
  cancelQuestion: string;
  chargeNotice: string;
  confirmCancel: string;
  keepBooking: string;
  regularPrice: string;
  youSave: string;
  promotionApplied: string;
}

function earliestBeginDate(booking: Booking): Date {
  return booking.date_ranges
    .map((range) => parse(range.begin_date, "yyyy-MM-dd", new Date()))
    .reduce((earliest, current) => (current < earliest ? current : earliest));
}

function latestEndDate(booking: Booking): Date {
  return booking.date_ranges
    .map((range) => parse(range.end_date, "yyyy-MM-dd", new Date()))
    .reduce((latest, current) => (current > latest ? current : latest));
}

function chargeReasonLabel(reason: BookingCharge["reason"], dict: BookingDetailsDict): string {
  switch (reason) {
    case "initial_charge":
      return dict.chargeReasonInitial;
    case "scheduled_accrual":
      return dict.chargeReasonAccrual;
    case "cancellation_settlement":
      return dict.chargeReasonSettlement;
  }
}

export default function BookingDetailsModal({
  booking,
  display,
  dict,
  lang,
  onClose,
  onCancel,
}: {
  booking: Booking;
  display: BookingDisplay;
  dict: BookingDetailsDict;
  lang: Locale;
  onClose: () => void;
  onCancel: (booking: Booking) => Promise<void>;
}) {
  const { currency: preferredCurrency } = useCurrency();
  const dateFnsLocale = DATE_FNS_LOCALES[lang];
  const [confirming, setConfirming] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const price = (amount: number) => formatPrice(amount, preferredCurrency);

  // display.charges/charge_schedule are index-aligned with booking's own
  // (unfiltered) lists — pair them up before filtering by status so the
  // amount for each entry still lines up after the filter. Entries without
  // a converted amount are dropped: cancelling from here adds a settlement
  // charge to the booking right away, while its display amount only arrives
  // with the follow-up currency-conversion request.
  const paidCharges = booking.charges
    .map((charge, i) => ({ charge, amount: display.charges[i] }))
    .filter((entry) => entry.charge.status === "succeeded" && entry.amount !== undefined);
  const upcomingCharges = booking.charge_schedule
    .map((entry, i) => ({ entry, amount: display.charge_schedule[i] }))
    .filter((x) => x.entry.status === "pending" && x.amount !== undefined);

  const isCancelled = booking.status === "Cancelled";
  const refundPercentage = applicableRefundPercentage(
    booking.cancellation_policy.rules,
    differenceInCalendarDays(earliestBeginDate(booking), new Date())
  );
  const chargePercentage = 1 - refundPercentage;
  // display.total_price is already converted server-side; the refund
  // percentage is plain arithmetic, not currency exchange.
  const chargeAmount = display.total_price * chargePercentage;
  // Same gradient scale as the cancellation timeline bars, keyed by the
  // underlying refund rate so the colors line up with that visualization.
  const chargeFill = fillForRefund(refundPercentage);

  const handleCancel = () => {
    setCancelling(true);
    setCancelError(null);
    onCancel(booking)
      // The parent re-renders us with the now-cancelled booking, so the
      // footer falls back to the cancelled state on its own.
      .then(() => setConfirming(false))
      .catch((err) => setCancelError(err instanceof ApiError ? err.message : String(err)))
      .finally(() => setCancelling(false));
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[110] flex items-center justify-center bg-black/50 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden">
        <div
          className="px-6 py-4 rounded-t-2xl flex items-center justify-between shrink-0"
          style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
        >
          <h2 className="text-lg font-bold text-white">{dict.title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={dict.close}
            className="text-white/80 hover:text-white text-xl leading-none cursor-pointer"
          >
            ×
          </button>
        </div>

        <div className="p-6 overflow-y-auto space-y-6">
          {/* Dates */}
          <div className="flex items-center justify-between text-sm">
            <div>
              <p className="text-gray-400 dark:text-gray-500 text-xs">{dict.checkIn}</p>
              <p className="font-semibold text-gray-900 dark:text-gray-100">
                {format(earliestBeginDate(booking), "dd/MM/yyyy")}
              </p>
            </div>
            <div className="text-right">
              <p className="text-gray-400 dark:text-gray-500 text-xs">{dict.checkOut}</p>
              <p className="font-semibold text-gray-900 dark:text-gray-100">
                {format(latestEndDate(booking), "dd/MM/yyyy")}
              </p>
            </div>
          </div>

          {/* Price breakdown */}
          <div>
            <p className="font-semibold text-sm text-gray-600 dark:text-gray-300 mb-2">{dict.priceBreakdown}</p>
            <div className="rounded-xl border border-gray-100 dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-700">
              {booking.date_ranges.map((range, i) => {
                const from = parse(range.begin_date, "yyyy-MM-dd", new Date());
                const to = parse(range.end_date, "yyyy-MM-dd", new Date());
                const nights = differenceInCalendarDays(to, from);
                const rangeDisplay = display.date_ranges[i];
                const perNight = nights > 0 ? rangeDisplay.price / nights : rangeDisplay.price;
                return (
                  <div key={i} className="px-4 py-2.5 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-gray-700 dark:text-gray-300">
                        {format(from, "dd/MM/yyyy")} → {format(to, "dd/MM/yyyy")}
                        <span className="text-gray-400 dark:text-gray-500 ml-2">
                          ({nights} {nights !== 1 ? dict.nights : dict.night}, {dict.averageNightly.replace("{price}", price(perNight))})
                        </span>
                      </span>
                      <span className="inline-flex items-baseline font-semibold text-gray-900 dark:text-gray-100">
                        <PriceWithDiscount
                          price={rangeDisplay.price}
                          regularPrice={rangeDisplay.regular_price}
                          currency={preferredCurrency}
                        />
                      </span>
                    </div>
                    {/* The promotions as they applied when this booking was
                        made — read from the snapshot stored on it, so a
                        promotion since edited or deleted still explains the
                        price the guest agreed to. */}
                    {range.applied_promotions.map((promotion, j) => (
                      <p key={j} className="mt-1 text-xs text-violet-700 dark:text-violet-400">
                        {dict.promotionApplied
                          .replace("{name}", promotion.name)
                          .replace("{nights}", String(promotion.nights))
                          // discount_total is denominated in the BOOKING's
                          // currency, not the display one — and no amount is
                          // ever converted on the client, so it is labelled
                          // with the currency it is actually in. The
                          // converted saving is the "you save" line below,
                          // which the server computes.
                          .replace("{amount}", formatPrice(promotion.discount_total, booking.currency))}
                      </p>
                    ))}
                  </div>
                );
              })}
              <div className="px-4 py-2.5 flex items-center justify-between text-sm bg-gray-50 dark:bg-gray-900/40">
                <span className="font-semibold text-gray-700 dark:text-gray-300">{dict.totalPrice}</span>
                <span className="inline-flex items-baseline font-bold text-gray-900 dark:text-gray-100">
                  <PriceWithDiscount
                    price={display.total_price}
                    regularPrice={display.total_regular_price}
                    currency={preferredCurrency}
                  />
                </span>
              </div>
              {display.total_discount > 0 && (
                <div className="px-4 py-2.5 flex items-center justify-between text-sm">
                  <span className="text-gray-500 dark:text-gray-400">{dict.regularPrice}</span>
                  <span className="font-semibold text-teal-700 dark:text-teal-400">
                    {dict.youSave.replace("{amount}", price(display.total_discount))}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Cancellation policy */}
          <div>
            <p className="font-semibold text-sm text-gray-600 dark:text-gray-300 mb-1">
              {dict.cancellationPolicy}: {booking.cancellation_policy.name}
            </p>
            {/* price stays display.total_price — the discounted figure. A
                refund is computed off what the guest actually pays, not off
                the struck-through regular price. */}
            <CancellationTimeline
              rules={booking.cancellation_policy.rules}
              checkInDate={earliestBeginDate(booking)}
              today={new Date()}
              dateLocale={dateFnsLocale}
              price={display.total_price}
              currency={preferredCurrency}
              cancellationLabel={dict.cancellationLabel}
              tillTemplate={dict.cancellationTill}
              rangeTemplate={dict.cancellationRange}
              freeLabel={dict.cancellationFree}
              chargeTemplate={dict.cancellationCharge}
            />
          </div>

          {/* Payment info */}
          <div>
            <p className="font-semibold text-sm text-gray-600 dark:text-gray-300 mb-2">{dict.paymentInfo}</p>

            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 mt-3 mb-1">{dict.paidSection}</p>
            {paidCharges.length === 0 ? (
              <p className="text-sm text-gray-400 dark:text-gray-500">{dict.noPayments}</p>
            ) : (
              <ul className="space-y-1">
                {paidCharges.map(({ charge, amount }, i) => (
                  <li key={i} className="flex items-center justify-between text-sm">
                    <span className="text-gray-700 dark:text-gray-300">
                      {format(parseISO(charge.created_at), "dd/MM/yyyy")}
                      <span className="text-gray-400 dark:text-gray-500 ml-2">
                        ({chargeReasonLabel(charge.reason, dict)})
                      </span>
                    </span>
                    <span className="font-semibold text-gray-900 dark:text-gray-100">{price(amount.amount)}</span>
                  </li>
                ))}
              </ul>
            )}

            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 mt-3 mb-1">{dict.upcomingSection}</p>
            {upcomingCharges.length === 0 ? (
              <p className="text-sm text-gray-400 dark:text-gray-500">{dict.noUpcomingCharges}</p>
            ) : (
              <ul className="space-y-1">
                {upcomingCharges.map(({ entry, amount }, i) => (
                  <li key={i} className="flex items-center justify-between text-sm">
                    <span className="text-gray-700 dark:text-gray-300">
                      {format(parse(entry.charge_date, "yyyy-MM-dd", new Date()), "dd/MM/yyyy")}
                    </span>
                    <span className="font-semibold text-gray-900 dark:text-gray-100">{price(amount.amount)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="px-6 py-4 border-t border-gray-100 dark:border-gray-700 shrink-0 space-y-3">
          {!isCancelled && confirming && (
            <>
              <p className="text-sm text-gray-700 dark:text-gray-300">
                {(() => {
                  const [before, after] = dict.chargeNotice.split("{amount}");
                  return (
                    <>
                      {before}
                      <span
                        className="font-semibold"
                        style={{ color: `rgb(${chargeFill[0]}, ${chargeFill[1]}, ${chargeFill[2]})` }}
                      >
                        {price(chargeAmount)} ({Math.round(chargePercentage * 100)}%)
                      </span>
                      {after}
                    </>
                  );
                })()}
              </p>
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{dict.cancelQuestion}</p>
            </>
          )}
          {cancelError && <p className="text-xs text-red-600 dark:text-red-400">{cancelError}</p>}

          <div className="flex items-center justify-end gap-2">
            {isCancelled ? (
              <p className="mr-auto text-xs font-semibold text-red-500 dark:text-red-400">{dict.cancelledStatus}</p>
            ) : confirming ? (
              <>
                <button
                  type="button"
                  onClick={() => setConfirming(false)}
                  disabled={cancelling}
                  className="px-4 py-2 rounded-lg text-sm font-semibold text-gray-600 dark:text-gray-300 border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer disabled:opacity-50"
                >
                  {dict.keepBooking}
                </button>
                <button
                  type="button"
                  onClick={handleCancel}
                  disabled={cancelling}
                  className="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-red-600 hover:bg-red-700 cursor-pointer disabled:opacity-50"
                >
                  {dict.confirmCancel}
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => {
                  setCancelError(null);
                  setConfirming(true);
                }}
                className="px-4 py-2 rounded-lg text-sm font-semibold text-red-600 dark:text-red-400 border border-red-200 dark:border-red-900 hover:bg-red-50 dark:hover:bg-red-950/40 cursor-pointer"
              >
                {dict.confirmCancel}
              </button>
            )}
            {!confirming && (
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-teal-700 hover:bg-teal-800 cursor-pointer"
              >
                {dict.close}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
