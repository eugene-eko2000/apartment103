"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { format, differenceInCalendarDays, parse } from "date-fns";
import { ApiError, cancelBooking, listBookings, listBookingsDisplay, type Booking, type BookingDisplay } from "@/lib/api";
import { formatPrice } from "@/lib/currency-config";
import { useCurrency } from "@/lib/currency-context";
import { applicableRefundPercentage } from "@/lib/refund";
import { readGuestSession } from "@/lib/guest-auth";
import { fillForRefund } from "@/components/CancellationTimeline";
import PriceWithDiscount from "@/components/PriceWithDiscount";
import BookingDetailsModal, { type BookingDetailsDict } from "@/components/BookingDetailsModal";
import type { Locale } from "@/lib/i18n-config";

export interface MyBookingsDict {
  close: string;
  title: string;
  loading: string;
  empty: string;
  loggedOut: string;
  bookedOn: string;
  cancellationPolicy: string;
  night: string;
  nights: string;
  cancelledStatus: string;
  cancelButton: string;
  cancelQuestion: string;
  chargeNotice: string;
  confirmCancel: string;
  keepBooking: string;
  regularPrice: string;
  // The details modal reuses the cancellation strings defined above rather
  // than duplicating them in every locale file.
  detailsModal: Omit<
    BookingDetailsDict,
    "cancelledStatus" | "cancelQuestion" | "chargeNotice" | "confirmCancel" | "keepBooking"
  >;
}

type Status = "loading" | "loggedOut" | "loaded" | "error";

function earliestBeginDate(booking: Booking): Date {
  return booking.date_ranges
    .map((range) => parse(range.begin_date, "yyyy-MM-dd", new Date()))
    .reduce((earliest, current) => (current < earliest ? current : earliest));
}

export default function MyBookingsModal({
  dict,
  lang,
  onClose,
}: {
  dict: MyBookingsDict;
  lang: Locale;
  onClose: () => void;
}) {
  const [status, setStatus] = useState<Status>("loading");
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [displays, setDisplays] = useState<Record<string, BookingDisplay>>({});
  const [displaysLoading, setDisplaysLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [detailsBooking, setDetailsBooking] = useState<Booking | null>(null);
  const { currency: preferredCurrency } = useCurrency();

  const refreshDisplays = () => {
    const session = readGuestSession();
    if (!session) return;
    listBookingsDisplay(session.token, preferredCurrency)
      .then((result) => {
        setDisplays(result);
        setDisplaysLoading(false);
      })
      .catch(() => setDisplaysLoading(false));
  };

  // Shared by the list row and the details modal; the caller decides how to
  // surface a rejection.
  const runCancel = (booking: Booking): Promise<void> => {
    const session = readGuestSession();
    if (!session) {
      setStatus("loggedOut");
      return Promise.reject(new Error(dict.loggedOut));
    }
    setCancellingId(booking._id);
    return cancelBooking(booking._id, session.token)
      .then((updated) => {
        setBookings((prev) => prev.map((b) => (b._id === updated._id ? updated : b)));
        // Cancellation can add a settlement charge, so the display amounts
        // (paid/upcoming breakdown) for this booking may now be stale.
        refreshDisplays();
      })
      .finally(() => setCancellingId(null));
  };

  const handleCancelConfirm = (booking: Booking) => {
    setCancelError(null);
    runCancel(booking)
      .then(() => setConfirmingId(null))
      .catch((err) => setCancelError(err instanceof ApiError ? err.message : String(err)));
  };

  useEffect(() => {
    // Deferred to a microtask so the localStorage read (and resulting
    // setState) isn't synchronous within the effect body, avoiding a
    // same-tick cascading render.
    queueMicrotask(() => {
      const session = readGuestSession();
      if (!session) {
        setStatus("loggedOut");
        return;
      }
      listBookings(session.token)
        .then((result) => {
          setBookings(result);
          setStatus("loaded");
        })
        .catch((err) => {
          setErrorMessage(err instanceof ApiError ? err.message : String(err));
          setStatus("error");
        });
    });
  }, []);

  // Amounts are computed server-side (Stripe FX rate + commission — see
  // backend/app/services/currency_service.py); re-fetch whenever the
  // guest's preferred display currency changes.
  useEffect(() => {
    if (status !== "loaded") return;
    setDisplaysLoading(true);
    refreshDisplays();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, preferredCurrency]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  // Portaled to the document body: this modal can be opened from inside the
  // header, whose backdrop-blur establishes a containing block for
  // position:fixed descendants — without the portal, "fixed inset-0" would
  // be positioned relative to the (much smaller) header bar instead of the
  // viewport.
  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
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

        <div className="p-6 overflow-y-auto">
          {status === "loading" && <p className="text-gray-500 dark:text-gray-400 text-sm">{dict.loading}</p>}
          {status === "loggedOut" && <p className="text-gray-500 dark:text-gray-400 text-sm">{dict.loggedOut}</p>}
          {status === "error" && <p className="text-red-600 dark:text-red-400 text-sm">{errorMessage}</p>}
          {status === "loaded" && bookings.length === 0 && (
            <p className="text-gray-500 dark:text-gray-400 text-sm">{dict.empty}</p>
          )}
          {/* Amounts come from a separate, currency-aware request
              (refreshDisplays) that lands shortly after the bookings list
              itself; this only covers that brief window. */}
          {status === "loaded" && bookings.length > 0 && displaysLoading && (
            <p className="text-gray-500 dark:text-gray-400 text-sm">{dict.loading}</p>
          )}

          {status === "loaded" && bookings.length > 0 && !displaysLoading && (
            <ul className="space-y-4">
              {bookings.map((booking) => {
                const display = displays[booking._id];
                if (!display) return null;
                const isCancelled = booking.status === "Cancelled";
                const isConfirming = confirmingId === booking._id;
                const refundPercentage = applicableRefundPercentage(
                  booking.cancellation_policy.rules,
                  differenceInCalendarDays(earliestBeginDate(booking), new Date())
                );
                const chargePercentage = 1 - refundPercentage;
                // display.total_price is already converted server-side; the
                // refund percentage is plain arithmetic, not currency exchange.
                const chargeAmount = display.total_price * chargePercentage;
                // Same gradient scale as the cancellation timeline bars, keyed by the
                // underlying refund rate so the colors line up with that visualization.
                const chargeFill = fillForRefund(refundPercentage);

                return (
                <li
                  key={booking._id}
                  onClick={() => setDetailsBooking(booking)}
                  className={`bg-gray-50 dark:bg-gray-900/40 rounded-2xl border border-gray-100 dark:border-gray-700 p-5 cursor-pointer hover:border-teal-300 dark:hover:border-teal-600 transition-colors ${isCancelled ? "opacity-60" : ""}`}
                >
                  {booking.date_ranges.map((range, i) => {
                    const from = parse(range.begin_date, "yyyy-MM-dd", new Date());
                    const to = parse(range.end_date, "yyyy-MM-dd", new Date());
                    const nights = differenceInCalendarDays(to, from);
                    return (
                      <div
                        key={i}
                        className="flex items-center justify-between text-sm py-1.5 first:pt-0 last:pb-0"
                      >
                        <span className="text-gray-700 dark:text-gray-300">
                          {format(from, "dd/MM/yyyy")} → {format(to, "dd/MM/yyyy")}
                          <span className="text-gray-400 dark:text-gray-500 ml-2">
                            ({nights} {nights !== 1 ? dict.nights : dict.night})
                          </span>
                        </span>
                        <span className="inline-flex items-baseline font-semibold text-gray-900 dark:text-gray-100">
                          <PriceWithDiscount
                            price={display.date_ranges[i].price}
                            regularPrice={display.date_ranges[i].regular_price}
                            currency={preferredCurrency}
                          />
                        </span>
                      </div>
                    );
                  })}
                  {display.total_discount > 0 && (
                    <div className="flex items-center justify-between text-sm py-1.5 border-t border-gray-100 dark:border-gray-700 mt-1.5 pt-2.5">
                      <span className="text-gray-500 dark:text-gray-400">{dict.regularPrice}</span>
                      <span className="inline-flex items-baseline font-semibold text-gray-900 dark:text-gray-100">
                        <PriceWithDiscount
                          price={display.total_price}
                          regularPrice={display.total_regular_price}
                          currency={preferredCurrency}
                        />
                      </span>
                    </div>
                  )}
                  <div className="text-xs text-gray-400 dark:text-gray-500 mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 flex items-center justify-between">
                    <span>{dict.bookedOn.replace("{date}", format(parse(booking.booking_date, "yyyy-MM-dd", new Date()), "dd/MM/yyyy"))}</span>
                    <span>{dict.cancellationPolicy}: {booking.cancellation_policy.name}</span>
                  </div>

                  {isCancelled && (
                    <p className="mt-3 text-xs font-semibold text-red-500 dark:text-red-400">{dict.cancelledStatus}</p>
                  )}

                  {!isCancelled && !isConfirming && (
                    <div className="mt-3 flex justify-end">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setCancelError(null);
                          setConfirmingId(booking._id);
                        }}
                        className="text-xs font-semibold text-red-600 dark:text-red-400 hover:underline cursor-pointer"
                      >
                        {dict.cancelButton}
                      </button>
                    </div>
                  )}

                  {!isCancelled && isConfirming && (
                    <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 space-y-2">
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
                                {formatPrice(chargeAmount, preferredCurrency)} ({Math.round(chargePercentage * 100)}%)
                              </span>
                              {after}
                            </>
                          );
                        })()}
                      </p>
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{dict.cancelQuestion}</p>
                      {cancelError && <p className="text-xs text-red-600 dark:text-red-400">{cancelError}</p>}
                      <div className="flex justify-end gap-2 pt-1">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmingId(null);
                          }}
                          disabled={cancellingId === booking._id}
                          className="px-3 py-1.5 rounded-lg text-xs font-semibold text-gray-600 dark:text-gray-300 border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer disabled:opacity-50"
                        >
                          {dict.keepBooking}
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleCancelConfirm(booking);
                          }}
                          disabled={cancellingId === booking._id}
                          className="px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-red-600 hover:bg-red-700 cursor-pointer disabled:opacity-50"
                        >
                          {dict.confirmCancel}
                        </button>
                      </div>
                    </div>
                  )}
                </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      {detailsBooking && displays[detailsBooking._id] && (
        <BookingDetailsModal
          booking={bookings.find((b) => b._id === detailsBooking._id) ?? detailsBooking}
          display={displays[detailsBooking._id]}
          dict={{
            ...dict.detailsModal,
            cancelledStatus: dict.cancelledStatus,
            cancelQuestion: dict.cancelQuestion,
            chargeNotice: dict.chargeNotice,
            confirmCancel: dict.confirmCancel,
            keepBooking: dict.keepBooking,
          }}
          lang={lang}
          onClose={() => setDetailsBooking(null)}
          onCancel={runCancel}
        />
      )}
    </div>,
    document.body
  );
}
