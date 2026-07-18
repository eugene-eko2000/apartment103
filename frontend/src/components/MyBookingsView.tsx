"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { format, differenceInCalendarDays, parse } from "date-fns";
import type { Locale } from "@/lib/i18n-config";
import { ApiError, listBookings, type Booking } from "@/lib/api";
import { formatPrice } from "@/lib/currency-config";
import { readGuestSession } from "@/lib/guest-auth";

export interface MyBookingsDict {
  title: string;
  loading: string;
  empty: string;
  loggedOut: string;
  backHome: string;
  bookedOn: string;
  cancellationPolicy: string;
  night: string;
  nights: string;
}

type Status = "loading" | "loggedOut" | "loaded" | "error";

export default function MyBookingsView({ dict, lang }: { dict: MyBookingsDict; lang: Locale }) {
  const [status, setStatus] = useState<Status>("loading");
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

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

  return (
    <div className="w-full max-w-3xl mx-auto px-6 py-10 min-h-screen">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{dict.title}</h1>
        <Link href={`/${lang}`} className="text-sm text-teal-700 dark:text-teal-400 hover:text-teal-800 dark:hover:text-teal-300 transition-colors">
          {dict.backHome}
        </Link>
      </div>

      {status === "loading" && <p className="text-gray-500 dark:text-gray-400 text-sm">{dict.loading}</p>}
      {status === "loggedOut" && <p className="text-gray-500 dark:text-gray-400 text-sm">{dict.loggedOut}</p>}
      {status === "error" && <p className="text-red-600 dark:text-red-400 text-sm">{errorMessage}</p>}
      {status === "loaded" && bookings.length === 0 && (
        <p className="text-gray-500 dark:text-gray-400 text-sm">{dict.empty}</p>
      )}

      {status === "loaded" && bookings.length > 0 && (
        <ul className="space-y-4">
          {bookings.map((booking) => (
            <li key={booking._id} className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-5">
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
                      {formatPrice(range.price, booking.currency)}
                    </span>
                  </div>
                );
              })}
              <div className="text-xs text-gray-400 dark:text-gray-500 mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 flex items-center justify-between">
                <span>{dict.bookedOn.replace("{date}", format(parse(booking.booking_date, "yyyy-MM-dd", new Date()), "dd/MM/yyyy"))}</span>
                <span>{dict.cancellationPolicy}: {booking.cancellation_policy.name}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
