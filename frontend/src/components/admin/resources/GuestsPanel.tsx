"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  createGuest,
  deleteGuest,
  listGuests,
  updateGuest,
  type Currency,
  type Guest,
  type GuestInput,
  type Language,
} from "@/lib/api";
import { useAdminAuth } from "@/lib/admin-auth";
import { DataTable, type Column } from "../DataTable";
import { Modal } from "../Modal";
import { SelectField, SubmitButton, TextField } from "../FormFields";

const LANGUAGES: Language[] = ["en", "de", "fr", "it"];
const CURRENCIES: Currency[] = ["EUR", "CHF", "USD", "GBP"];

const emptyForm: GuestInput = {
  family_name: "",
  first_name: "",
  residence_address: { street_address: "", zip: "", city: "", state: "", country: "" },
  phone_number: "",
  email: "",
  preferred_language: null,
  preferred_currency: null,
};

function guestToForm(guest: Guest): GuestInput {
  return {
    family_name: guest.family_name,
    first_name: guest.first_name,
    residence_address: { ...guest.residence_address, state: guest.residence_address.state ?? "" },
    phone_number: guest.phone_number,
    email: guest.email,
    preferred_language: guest.preferred_language ?? null,
    preferred_currency: guest.preferred_currency ?? null,
  };
}

export default function GuestsPanel() {
  const { session, logout } = useAdminAuth();
  const token = session!.token;

  const [guests, setGuests] = useState<Guest[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [editing, setEditing] = useState<Guest | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<GuestInput>(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const load = () => {
    listGuests(token)
      .then((data) => {
        setGuests(data);
        setListError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) return logout();
        setListError(err instanceof ApiError ? err.message : String(err));
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setFormError(null);
    setShowModal(true);
  };

  const openEdit = (guest: Guest) => {
    setEditing(guest);
    setForm(guestToForm(guest));
    setFormError(null);
    setShowModal(true);
  };

  const handleDelete = async (guest: Guest) => {
    if (!window.confirm(`Delete guest ${guest.first_name} ${guest.family_name}?`)) return;
    try {
      await deleteGuest(guest._id, token);
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      window.alert(err instanceof ApiError ? err.message : String(err));
    }
  };

  const handleSubmit = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    setPending(true);
    setFormError(null);
    try {
      if (editing) {
        await updateGuest(editing._id, token, form);
      } else {
        await createGuest(token, form);
      }
      setShowModal(false);
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      setFormError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setPending(false);
    }
  };

  const updateAddress = (field: keyof GuestInput["residence_address"], value: string) => {
    setForm((prev) => ({ ...prev, residence_address: { ...prev.residence_address, [field]: value } }));
  };

  const columns: Column<Guest>[] = [
    { key: "name", label: "Name", render: (g) => `${g.first_name} ${g.family_name}` },
    { key: "email", label: "Email", render: (g) => g.email },
    { key: "phone", label: "Phone", render: (g) => g.phone_number },
    {
      key: "location",
      label: "Location",
      render: (g) => `${g.residence_address.city}, ${g.residence_address.country}`,
    },
  ];

  return (
    <div>
      <DataTable
        columns={columns}
        rows={guests}
        rowKey={(g) => g._id}
        onEdit={openEdit}
        onDelete={handleDelete}
        onCreate={openCreate}
        createLabel="New guest"
        loading={loading}
        error={listError}
      />

      {showModal && (
        <Modal title={editing ? "Edit guest" : "New guest"} onClose={() => setShowModal(false)}>
          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <TextField
                label="First name"
                value={form.first_name}
                onChange={(v) => setForm((p) => ({ ...p, first_name: v }))}
              />
              <TextField
                label="Family name"
                value={form.family_name}
                onChange={(v) => setForm((p) => ({ ...p, family_name: v }))}
              />
            </div>
            <TextField
              label="Email"
              type="email"
              value={form.email}
              onChange={(v) => setForm((p) => ({ ...p, email: v }))}
            />
            <TextField
              label="Phone number"
              value={form.phone_number}
              onChange={(v) => setForm((p) => ({ ...p, phone_number: v }))}
            />
            <TextField
              label="Street address"
              value={form.residence_address.street_address}
              onChange={(v) => updateAddress("street_address", v)}
            />
            <div className="grid grid-cols-2 gap-3">
              <TextField label="ZIP" value={form.residence_address.zip} onChange={(v) => updateAddress("zip", v)} />
              <TextField label="City" value={form.residence_address.city} onChange={(v) => updateAddress("city", v)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <TextField
                label="State (optional)"
                value={form.residence_address.state ?? ""}
                onChange={(v) => updateAddress("state", v)}
                required={false}
              />
              <TextField
                label="Country"
                value={form.residence_address.country}
                onChange={(v) => updateAddress("country", v)}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <SelectField
                label="Preferred language"
                value={form.preferred_language ?? ""}
                noneLabel="No preference"
                options={LANGUAGES.map((l) => ({ value: l, label: l.toUpperCase() }))}
                onChange={(v) => setForm((p) => ({ ...p, preferred_language: (v || null) as Language | null }))}
              />
              <SelectField
                label="Preferred currency"
                value={form.preferred_currency ?? ""}
                noneLabel="No preference"
                options={CURRENCIES.map((c) => ({ value: c, label: c }))}
                onChange={(v) => setForm((p) => ({ ...p, preferred_currency: (v || null) as Currency | null }))}
              />
            </div>
            {formError && <p className="text-sm text-red-600">{formError}</p>}
            <SubmitButton pending={pending} label={editing ? "Save changes" : "Create guest"} />
          </form>
        </Modal>
      )}
    </div>
  );
}
