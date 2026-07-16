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

const emptyDateRange = (): BookingDateRange => ({ begin_date: "", end_date: "", price: 0 });

function emptyForm(guestId: string, policyId: string): BookingInput {
  return { guest_id: guestId, cancellation_policy_id: policyId, currency: "CHF", date_ranges: [] };
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

  const handleSubmit = async (e: React.FormEvent) => {
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
  ];

  return (
    <div>
      <DataTable
        columns={columns}
        rows={bookings}
        rowKey={(b) => b._id}
        onEdit={openEdit}
        onDelete={handleDelete}
        onCreate={() => window.alert("New bookings are created through the public booking widget.")}
        createLabel="New booking"
        loading={loading}
        error={listError}
        emptyLabel="No bookings yet."
      />

      {showModal && editing && (
        <Modal title="Edit booking" onClose={() => setShowModal(false)}>
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
            {formError && <p className="text-sm text-red-600">{formError}</p>}
            <SubmitButton pending={pending} label="Save changes" />
          </form>
        </Modal>
      )}
    </div>
  );
}
