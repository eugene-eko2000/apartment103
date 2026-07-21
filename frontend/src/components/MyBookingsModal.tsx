"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { format, differenceInCalendarDays, parse } from "date-fns";
import { ApiError, cancelBooking, listBookings, type Booking } from "@/lib/api";
import { convertCurrency, formatPrice } from "@/lib/currency-config";
import { useCurrency } from "@/lib/currency-context";
import { applicableRefundPercentage } from "@/lib/refund";
import { readGuestSession } from "@/lib/guest-auth";

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
  refundNotice: string;
  confirmCancel: string;
  keepBooking: string;
}

type Status = "loading" | "loggedOut" | "loaded" | "error";

function earliestBeginDate(booking: Booking): Date {
  return booking.date_ranges
    .map((range) => parse(range.begin_date, "yyyy-MM-dd", new Date()))
    .reduce((earliest, current) => (current < earliest ? current : earliest));
}

function totalPrice(booking: Booking): number {
  return booking.date_ranges.reduce((sum, range) => sum + range.price, 0);
}

export default function MyBookingsModal({ dict, onClose }: { dict: MyBookingsDict; onClose: () => void }) {
  const [status, setStatus] = useState<Status>("loading");
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const { currency: preferredCurrency } = useCurrency();

  const handleCancelConfirm = (booking: Booking) => {
    const session = readGuestSession();
    if (!session) {
      setStatus("loggedOut");
      return;
    }
    setCancellingId(booking._id);
    setCancelError(null);
    cancelBooking(booking._id, session.token)
      .then((updated) => {
        setBookings((prev) => prev.map((b) => (b._id === updated._id ? updated : b)));
        setConfirmingId(null);
      })
      .catch((err) => {
        setCancelError(err instanceof ApiError ? err.message : String(err));
      })
      .finally(() => setCancellingId(null));
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
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-y-auto">
        <div
          className="px-6 py-4 rounded-t-2xl flex items-center justify-between sticky top-0"
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

        <div className="p-6">
          {status === "loading" && <p className="text-gray-500 dark:text-gray-400 text-sm">{dict.loading}</p>}
          {status === "loggedOut" && <p className="text-gray-500 dark:text-gray-400 text-sm">{dict.loggedOut}</p>}
          {status === "error" && <p className="text-red-600 dark:text-red-400 text-sm">{errorMessage}</p>}
          {status === "loaded" && bookings.length === 0 && (
            <p className="text-gray-500 dark:text-gray-400 text-sm">{dict.empty}</p>
          )}

          {status === "loaded" && bookings.length > 0 && (
            <ul className="space-y-4">
              {bookings.map((booking) => {
                const isCancelled = booking.status === "Cancelled";
                const isConfirming = confirmingId === booking._id;
                const refundPercentage = applicableRefundPercentage(
                  booking.cancellation_policy.rules,
                  differenceInCalendarDays(earliestBeginDate(booking), new Date())
                );
                const refundAmount = convertCurrency(
                  totalPrice(booking) * refundPercentage,
                  booking.currency,
                  preferredCurrency
                );

                return (
                <li key={booking._id} className={`bg-gray-50 dark:bg-gray-900/40 rounded-2xl border border-gray-100 dark:border-gray-700 p-5 ${isCancelled ? "opacity-60" : ""}`}>
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
                        <span className="font-semibold text-gray-900 dark:text-gray-100">
                          {formatPrice(convertCurrency(range.price, booking.currency, preferredCurrency), preferredCurrency)}
                        </span>
                      </div>
                    );
                  })}
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
                        onClick={() => {
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
                        {dict.refundNotice
                          .replace("{amount}", formatPrice(refundAmount, preferredCurrency))
                          .replace("{percent}", String(Math.round(refundPercentage * 100)))}
                      </p>
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{dict.cancelQuestion}</p>
                      {cancelError && <p className="text-xs text-red-600 dark:text-red-400">{cancelError}</p>}
                      <div className="flex justify-end gap-2 pt-1">
                        <button
                          type="button"
                          onClick={() => setConfirmingId(null)}
                          disabled={cancellingId === booking._id}
                          className="px-3 py-1.5 rounded-lg text-xs font-semibold text-gray-600 dark:text-gray-300 border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer disabled:opacity-50"
                        >
                          {dict.keepBooking}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleCancelConfirm(booking)}
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
    </div>,
    document.body
  );
}
