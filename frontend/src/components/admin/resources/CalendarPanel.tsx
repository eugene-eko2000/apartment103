"use client";

import { useEffect, useMemo, useState } from "react";
import { DayPicker } from "react-day-picker";
import { parse } from "date-fns";
import "react-day-picker/style.css";
import { ApiError, listBookings, type Booking } from "@/lib/api";
import { useAdminAuth } from "@/lib/admin-auth";

const ISO_FORMAT = "yyyy-MM-dd";

function parseISODate(value: string): Date | undefined {
  const parsed = parse(value, ISO_FORMAT, new Date());
  return Number.isNaN(parsed.getTime()) ? undefined : parsed;
}

// Chosen to stay legible with the white day-number text used on booked days,
// in both light and dark theme.
const PALETTE = ["#4f46e5", "#0891b2", "#16a34a", "#ca8a04", "#db2777", "#7c3aed", "#dc2626", "#0d9488"];

function colorForBooking(bookingId: string): string {
  let hash = 0;
  for (let i = 0; i < bookingId.length; i++) hash = (hash * 31 + bookingId.charCodeAt(i)) | 0;
  return PALETTE[Math.abs(hash) % PALETTE.length];
}

interface BookingSegment {
  booking: Booking;
  from: Date;
  to: Date;
}

export default function CalendarPanel() {
  const { session, logout } = useAdminAuth();
  const token = session!.token;

  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);

  useEffect(() => {
    listBookings(token)
      .then((list) => {
        setBookings(list);
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
      bookings.flatMap((booking) =>
        booking.date_ranges
          .map((range) => {
            const from = parseISODate(range.begin_date);
            const to = parseISODate(range.end_date);
            return from && to ? { booking, from, to } : null;
          })
          .filter((s): s is BookingSegment => s !== null)
      ),
    [bookings]
  );

  const modifiers = useMemo(() => {
    const result: Record<string, { from: Date; to: Date }[]> = {};
    for (const segment of segments) {
      const key = `booking-${segment.booking._id}`;
      (result[key] ??= []).push({ from: segment.from, to: segment.to });
    }
    return result;
  }, [segments]);

  const modifiersStyles = useMemo(() => {
    const result: Record<string, React.CSSProperties> = {};
    for (const booking of bookings) {
      result[`booking-${booking._id}`] = { backgroundColor: colorForBooking(booking._id), color: "white" };
    }
    return result;
  }, [bookings]);

  const selectedSegments = selectedDate ? segments.filter((s) => selectedDate >= s.from && selectedDate <= s.to) : [];

  if (loading) return <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>;
  if (error) return <p className="text-sm text-red-600 dark:text-red-400">{error}</p>;

  return (
    <div className="flex flex-col lg:flex-row gap-8 items-start">
      <div
        className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 overflow-x-auto"
        style={
          {
            "--rdp-day-width": "56px",
            "--rdp-day-height": "56px",
            "--rdp-day_button-width": "52px",
            "--rdp-day_button-height": "52px",
            "--rdp-day_button-border-radius": "0.5rem",
            "--rdp-accent-color": "#4f46e5",
          } as React.CSSProperties
        }
      >
        <DayPicker
          modifiers={modifiers}
          modifiersStyles={modifiersStyles}
          onDayClick={(date) => setSelectedDate(date)}
          showOutsideDays
        />
      </div>

      <div className="w-full lg:w-72 space-y-6">
        <div>
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-2">
            {selectedDate ? selectedDate.toLocaleDateString() : "Select a day"}
          </h3>
          {selectedDate && selectedSegments.length === 0 && (
            <p className="text-sm text-slate-500 dark:text-slate-400">No bookings on this day.</p>
          )}
          <ul className="space-y-2">
            {selectedSegments.map((s) => (
              <li key={s.booking._id} className="flex items-center gap-2 text-sm">
                <span
                  className="w-3 h-3 rounded-full shrink-0"
                  style={{ backgroundColor: colorForBooking(s.booking._id) }}
                />
                <span className="text-slate-700 dark:text-slate-200">
                  {s.booking.guest.first_name} {s.booking.guest.family_name}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-2">Bookings</h3>
          {bookings.length === 0 && <p className="text-sm text-slate-500 dark:text-slate-400">No bookings yet.</p>}
          <ul className="space-y-3 max-h-96 overflow-y-auto">
            {bookings.map((b) => (
              <li key={b._id} className="flex items-start gap-2 text-sm">
                <span
                  className="w-3 h-3 rounded-full shrink-0 mt-1"
                  style={{ backgroundColor: colorForBooking(b._id) }}
                />
                <div>
                  <p className="text-slate-700 dark:text-slate-200">
                    {b.guest.first_name} {b.guest.family_name}
                  </p>
                  {b.date_ranges.map((r, i) => (
                    <p key={i} className="text-xs text-slate-500 dark:text-slate-400">
                      {r.begin_date} – {r.end_date}
                    </p>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
