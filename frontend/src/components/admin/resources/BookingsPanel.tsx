"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  deleteBooking,
  listBookings,
  listCancellationPolicies,
  listGuests,
  updateBooking,
  type Booking,
  type BookingDateRange,
  type BookingInput,
  type BookingWebhookEvent,
  type CancellationPolicy,
  type Currency,
  type Guest,
} from "@/lib/api";
import { useAdminAuth } from "@/lib/admin-auth";
import { DataTable, type Column } from "../DataTable";
import { Modal } from "../Modal";
import { NumberField, SelectField, SubmitButton, TextField } from "../FormFields";
import { RepeatingRows } from "../RepeatingRows";

const CURRENCIES: Currency[] = ["EUR", "CHF", "USD", "GBP"];

const PAYMENT_STATUS_LABELS: Record<Booking["payment_status"], string> = {
  card_verification_pending: "Awaiting card",
  card_verified: "Card verified",
  partially_charged: "Partially charged",
  fully_charged: "Fully charged",
  requires_action: "Needs guest action",
  failed: "Payment failed",
};

const PAYMENT_STATUS_CLASSES: Record<Booking["payment_status"], string> = {
  card_verification_pending: "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300",
  card_verified: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  partially_charged: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  fully_charged: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
  requires_action: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
};

const BOOKING_STATUS_CLASSES: Record<Booking["status"], string> = {
  Pending: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  Active: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
  Cancelled: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
};

const emptyDateRange = (): BookingDateRange => ({ begin_date: "", end_date: "", price: 0 });

function emptyForm(guestId: string, policyId: string): BookingInput {
  return { guest_id: guestId, cancellation_policy_id: policyId, currency: "CHF", date_ranges: [] };
}

function ReadOnlyField({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <span className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">{label}</span>
      <p className="text-sm text-slate-700 dark:text-slate-300 break-all">{value}</p>
    </div>
  );
}

function WebhookEventItem({ event }: { event: BookingWebhookEvent }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-slate-200 dark:border-slate-600 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-2 px-3 py-2 bg-slate-50 dark:bg-slate-700 text-left cursor-pointer"
      >
        <span className="text-xs text-slate-700 dark:text-slate-300 truncate">
          <span className="font-semibold">{event.event_type}</span>{" "}
          <span className="text-slate-400 dark:text-slate-500">{new Date(event.received_at).toLocaleString()}</span>
        </span>
        <span className="text-slate-400 dark:text-slate-500 text-xs shrink-0">{open ? "▲ Collapse" : "▼ Expand"}</span>
      </button>
      {open && (
        <div className="p-3 bg-white dark:bg-slate-800 space-y-2">
          <ReadOnlyField label="Stripe event ID" value={event.stripe_event_id} />
          <div>
            <span className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Raw payload</span>
            <pre className="text-xs bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg p-2 overflow-x-auto max-h-64 overflow-y-auto text-slate-700 dark:text-slate-300">
              {JSON.stringify(event.data, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

export default function BookingsPanel() {
  const { session, logout } = useAdminAuth();
  const token = session!.token;

  const [bookings, setBookings] = useState<Booking[]>([]);
  const [guests, setGuests] = useState<Guest[]>([]);
  const [policies, setPolicies] = useState<CancellationPolicy[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [editing, setEditing] = useState<Booking | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<BookingInput>(emptyForm("", ""));
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const load = () => {
    Promise.all([listBookings(token), listGuests(token), listCancellationPolicies(token)])
      .then(([bookingList, guestList, policyList]) => {
        setBookings(bookingList);
        setGuests(guestList);
        setPolicies(policyList);
        setListError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) return logout();
        setListError(err instanceof ApiError ? err.message : String(err));
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  // Bookings are created through the public booking widget (which also
  // snapshots pricing from a Plan); the admin panel focuses on managing
  // existing bookings rather than duplicating that flow, so there is no
  // "New booking" action here, only edit/delete.

  const openEdit = (booking: Booking) => {
    setEditing(booking);
    // Bookings only embed a snapshot of the cancellation policy (name +
    // rules), not its id, so the best we can do is match by name and let
    // the admin pick a different one if it no longer resolves.
    const matchingPolicy = policies.find((p) => p.name === booking.cancellation_policy.name);
    setForm({
      guest_id: booking.guest.id,
      cancellation_policy_id: matchingPolicy?._id ?? "",
      currency: booking.currency,
      date_ranges: booking.date_ranges,
    });
    setFormError(null);
    setShowModal(true);
  };

  const handleDelete = async (booking: Booking) => {
    if (!window.confirm(`Delete this booking for ${booking.guest.first_name} ${booking.guest.family_name}?`)) return;
    try {
      await deleteBooking(booking._id, token);
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      window.alert(err instanceof ApiError ? err.message : String(err));
    }
  };

  const handleBulkDelete = async (selectedBookings: Booking[]) => {
    if (!window.confirm(`Delete ${selectedBookings.length} booking${selectedBookings.length === 1 ? "" : "s"}?`)) return;
    try {
      await Promise.all(selectedBookings.map((b) => deleteBooking(b._id, token)));
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      window.alert(err instanceof ApiError ? err.message : String(err));
    }
  };

  const handleSubmit = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!editing) return;
    if (!form.cancellation_policy_id) {
      setFormError("Select a cancellation policy.");
      return;
    }
    setPending(true);
    setFormError(null);
    try {
      await updateBooking(editing._id, token, form);
      setShowModal(false);
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      setFormError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setPending(false);
    }
  };

  const columns: Column<Booking>[] = [
    { key: "guest", label: "Guest", render: (b) => `${b.guest.first_name} ${b.guest.family_name}` },
    { key: "date", label: "Booked on", render: (b) => b.booking_date },
    { key: "currency", label: "Currency", render: (b) => b.currency },
    {
      key: "total",
      label: "Total",
      render: (b) => b.date_ranges.reduce((sum, r) => sum + r.price, 0).toFixed(2),
    },
    { key: "policy", label: "Cancellation policy", render: (b) => b.cancellation_policy.name },
    {
      key: "payment",
      label: "Payment",
      render: (b) => (
        <span
          className={`inline-flex px-2 py-0.5 rounded-full text-xs font-semibold ${PAYMENT_STATUS_CLASSES[b.payment_status]}`}
          title={b.last_payment_error ?? undefined}
        >
          {PAYMENT_STATUS_LABELS[b.payment_status]} ({b.amount_charged.toFixed(2)}/
          {b.date_ranges.reduce((sum, r) => sum + r.price, 0).toFixed(2)})
        </span>
      ),
    },
    {
      key: "status",
      label: "Status",
      render: (b) => (
        <span
          className={`inline-flex px-2 py-0.5 rounded-full text-xs font-semibold ${BOOKING_STATUS_CLASSES[b.status]}`}
        >
          {b.status}
        </span>
      ),
    },
  ];

  return (
    <div>
      <DataTable
        columns={columns}
        rows={bookings}
        rowKey={(b) => b._id}
        onEdit={openEdit}
        onDelete={handleDelete}
        onBulkDelete={handleBulkDelete}
        onCreate={() => window.alert("New bookings are created through the public booking widget.")}
        createLabel="New booking"
        loading={loading}
        error={listError}
        emptyLabel="No bookings yet."
      />

      {showModal && editing && (
        <Modal title="Edit booking" onClose={() => setShowModal(false)} maxWidth="max-w-2xl">
          <form onSubmit={handleSubmit} className="space-y-4">
            <SelectField
              label="Guest"
              value={form.guest_id}
              options={guests.map((g) => ({ value: g._id, label: `${g.first_name} ${g.family_name}` }))}
              onChange={(v) => setForm((p) => ({ ...p, guest_id: v }))}
            />
            <SelectField
              label="Cancellation policy"
              value={form.cancellation_policy_id}
              options={policies.map((p) => ({ value: p._id, label: p.name }))}
              onChange={(v) => setForm((p) => ({ ...p, cancellation_policy_id: v }))}
            />
            <SelectField
              label="Currency"
              value={form.currency}
              options={CURRENCIES.map((c) => ({ value: c, label: c }))}
              onChange={(v) => setForm((p) => ({ ...p, currency: v }))}
            />
            <RepeatingRows<BookingDateRange>
              label="Stay date ranges"
              items={form.date_ranges}
              onChange={(date_ranges) => setForm((p) => ({ ...p, date_ranges }))}
              emptyRow={emptyDateRange}
              addLabel="Add date range"
              renderRow={(range, update) => (
                <>
                  <TextField
                    label="Begin date"
                    type="date"
                    value={range.begin_date}
                    onChange={(v) => update({ begin_date: v })}
                  />
                  <TextField
                    label="End date"
                    type="date"
                    value={range.end_date}
                    onChange={(v) => update({ end_date: v })}
                  />
                  <NumberField label="Price" value={range.price} min={0} step={0.01} onChange={(v) => update({ price: v })} />
                </>
              )}
            />

            <div className="border-t border-slate-200 dark:border-slate-700 pt-4 space-y-4">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
                Booking &amp; payment data
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <ReadOnlyField label="Booking ID" value={editing._id} />
                <ReadOnlyField label="Status" value={editing.status} />
                <ReadOnlyField label="Payment status" value={PAYMENT_STATUS_LABELS[editing.payment_status]} />
                <ReadOnlyField
                  label="Amount charged"
                  value={`${editing.amount_charged.toFixed(2)} / ${editing.date_ranges
                    .reduce((sum, r) => sum + r.price, 0)
                    .toFixed(2)} ${editing.currency}`}
                />
                <ReadOnlyField label="Stripe payment method" value={editing.stripe_payment_method_id ?? "—"} />
                <ReadOnlyField
                  label="Last payment check"
                  value={editing.last_payment_check_at ? new Date(editing.last_payment_check_at).toLocaleString() : "—"}
                />
                <ReadOnlyField label="Last payment error" value={editing.last_payment_error ?? "—"} />
              </div>

              <div>
                <span className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-2">
                  Charges ({editing.charges.length})
                </span>
                {editing.charges.length === 0 ? (
                  <p className="text-xs text-slate-400 dark:text-slate-500 italic">None yet.</p>
                ) : (
                  <div className="space-y-1.5">
                    {editing.charges.map((charge, i) => (
                      <div
                        key={i}
                        className="text-xs text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg px-3 py-2 flex flex-wrap gap-x-3 gap-y-0.5"
                      >
                        <span className="font-semibold">
                          {charge.amount.toFixed(2)} {charge.currency}
                        </span>
                        <span>{charge.reason}</span>
                        <span>{charge.status}</span>
                        <span className="text-slate-400 dark:text-slate-500">{new Date(charge.created_at).toLocaleString()}</span>
                        <span className="text-slate-400 dark:text-slate-500 break-all">{charge.stripe_payment_intent_id}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <span className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-2">
                  Webhook events ({editing.webhook_events.length})
                </span>
                {editing.webhook_events.length === 0 ? (
                  <p className="text-xs text-slate-400 dark:text-slate-500 italic">None yet.</p>
                ) : (
                  <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
                    {editing.webhook_events.map((event) => (
                      <WebhookEventItem key={event.stripe_event_id} event={event} />
                    ))}
                  </div>
                )}
              </div>
            </div>

            {formError && <p className="text-sm text-red-600 dark:text-red-400">{formError}</p>}
            <SubmitButton pending={pending} label="Save changes" />
          </form>
        </Modal>
      )}
    </div>
  );
}
