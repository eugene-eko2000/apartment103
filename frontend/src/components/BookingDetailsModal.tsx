"use client";

import { useEffect } from "react";
import { createPortal } from "react-dom";
import { format, differenceInCalendarDays, parse, parseISO } from "date-fns";
import { enUS, de, fr, it } from "date-fns/locale";
import type { Locale as DateFnsLocale } from "date-fns";
import type { Booking, BookingCharge } from "@/lib/api";
import { convertCurrency, formatPrice } from "@/lib/currency-config";
import { useCurrency } from "@/lib/currency-context";
import { CancellationTimeline } from "@/components/CancellationTimeline";
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

function totalPrice(booking: Booking): number {
  return booking.date_ranges.reduce((sum, range) => sum + range.price, 0);
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
  dict,
  lang,
  onClose,
}: {
  booking: Booking;
  dict: BookingDetailsDict;
  lang: Locale;
  onClose: () => void;
}) {
  const { currency: preferredCurrency } = useCurrency();
  const dateFnsLocale = DATE_FNS_LOCALES[lang];

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const price = (amount: number) => formatPrice(convertCurrency(amount, booking.currency, preferredCurrency), preferredCurrency);

  const paidCharges = booking.charges.filter((c) => c.status === "succeeded");
  const upcomingCharges = booking.charge_schedule.filter((e) => e.status === "pending");

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
                const perNight = nights > 0 ? range.price / nights : range.price;
                return (
                  <div key={i} className="px-4 py-2.5 flex items-center justify-between text-sm">
                    <span className="text-gray-700 dark:text-gray-300">
                      {format(from, "dd/MM/yyyy")} → {format(to, "dd/MM/yyyy")}
                      <span className="text-gray-400 dark:text-gray-500 ml-2">
                        ({nights} {nights !== 1 ? dict.nights : dict.night}, {dict.averageNightly.replace("{price}", price(perNight))})
                      </span>
                    </span>
                    <span className="font-semibold text-gray-900 dark:text-gray-100">{price(range.price)}</span>
                  </div>
                );
              })}
              <div className="px-4 py-2.5 flex items-center justify-between text-sm bg-gray-50 dark:bg-gray-900/40">
                <span className="font-semibold text-gray-700 dark:text-gray-300">{dict.totalPrice}</span>
                <span className="font-bold text-gray-900 dark:text-gray-100">{price(totalPrice(booking))}</span>
              </div>
            </div>
          </div>

          {/* Cancellation policy */}
          <div>
            <p className="font-semibold text-sm text-gray-600 dark:text-gray-300 mb-1">
              {dict.cancellationPolicy}: {booking.cancellation_policy.name}
            </p>
            <CancellationTimeline
              rules={booking.cancellation_policy.rules}
              checkInDate={earliestBeginDate(booking)}
              today={new Date()}
              dateLocale={dateFnsLocale}
              price={totalPrice(booking)}
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
                {paidCharges.map((charge, i) => (
                  <li key={i} className="flex items-center justify-between text-sm">
                    <span className="text-gray-700 dark:text-gray-300">
                      {format(parseISO(charge.created_at), "dd/MM/yyyy")}
                      <span className="text-gray-400 dark:text-gray-500 ml-2">
                        ({chargeReasonLabel(charge.reason, dict)})
                      </span>
                    </span>
                    <span className="font-semibold text-gray-900 dark:text-gray-100">
                      {formatPrice(convertCurrency(charge.amount, charge.currency, preferredCurrency), preferredCurrency)}
                    </span>
                  </li>
                ))}
              </ul>
            )}

            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 mt-3 mb-1">{dict.upcomingSection}</p>
            {upcomingCharges.length === 0 ? (
              <p className="text-sm text-gray-400 dark:text-gray-500">{dict.noUpcomingCharges}</p>
            ) : (
              <ul className="space-y-1">
                {upcomingCharges.map((entry, i) => (
                  <li key={i} className="flex items-center justify-between text-sm">
                    <span className="text-gray-700 dark:text-gray-300">
                      {format(parse(entry.charge_date, "yyyy-MM-dd", new Date()), "dd/MM/yyyy")}
                    </span>
                    <span className="font-semibold text-gray-900 dark:text-gray-100">{price(entry.amount)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
