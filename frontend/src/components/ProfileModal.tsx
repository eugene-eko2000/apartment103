"use client";

import { useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";
import { ApiError, getGuest, updateGuest, type Currency, type Guest, type GuestInput, type Language } from "@/lib/api";
import { readGuestSession } from "@/lib/guest-auth";
import { useApplyGuestPreferences } from "@/lib/guest-preferences";
import { PhoneInput } from "@/components/PhoneInput";

const LANGUAGES: Language[] = ["en", "de", "fr", "it"];
const CURRENCIES: Currency[] = ["EUR", "CHF", "USD", "GBP"];

export interface ProfileModalDict {
  close: string;
  title: string;
  loading: string;
  loggedOut: string;
  noProfile: string;
  firstName: string;
  familyName: string;
  email: string;
  phoneNumber: string;
  streetAddress: string;
  zip: string;
  city: string;
  stateOptional: string;
  country: string;
  preferredLanguage: string;
  preferredCurrency: string;
  noPreference: string;
  save: string;
  saving: string;
  saved: string;
}

type Status = "loading" | "loggedOut" | "noProfile" | "loaded" | "error";

// Mirrors BookingModal's guestToForm, converting a fetched Guest into the
// editable GuestInput shape this form works with.
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

export default function ProfileModal({ dict, onClose }: { dict: ProfileModalDict; onClose: () => void }) {
  const [status, setStatus] = useState<Status>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [form, setForm] = useState<GuestInput | null>(null);
  const [pending, setPending] = useState(false);
  const [saved, setSaved] = useState(false);
  const applyGuestPreferences = useApplyGuestPreferences();

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
      if (!session.guestId) {
        setStatus("noProfile");
        return;
      }
      getGuest(session.guestId, session.token)
        .then((guest) => {
          setForm(guestToForm(guest));
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

  const updateAddress = (key: keyof GuestInput["residence_address"], value: string) => {
    setForm((p) => (p ? { ...p, residence_address: { ...p.residence_address, [key]: value } } : p));
  };

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const session = readGuestSession();
    if (!session || !session.guestId || !form) return;
    setPending(true);
    setErrorMessage(null);
    setSaved(false);
    updateGuest(session.guestId, session.token, form)
      .then((guest) => {
        setForm(guestToForm(guest));
        setSaved(true);
        // The guest just told us their preferred language/currency — make it
        // the site's active one immediately, not just on their next visit.
        applyGuestPreferences(guest);
      })
      .catch((err) => {
        setErrorMessage(err instanceof ApiError ? err.message : String(err));
      })
      .finally(() => setPending(false));
  };

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
          {status === "noProfile" && <p className="text-gray-500 dark:text-gray-400 text-sm">{dict.noProfile}</p>}
          {status === "error" && <p className="text-red-600 dark:text-red-400 text-sm">{errorMessage}</p>}

          {status === "loaded" && form && (
            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <TextField
                  label={dict.firstName}
                  value={form.first_name}
                  onChange={(v) => setForm((p) => (p ? { ...p, first_name: v } : p))}
                />
                <TextField
                  label={dict.familyName}
                  value={form.family_name}
                  onChange={(v) => setForm((p) => (p ? { ...p, family_name: v } : p))}
                />
                <TextField
                  label={dict.email}
                  type="email"
                  value={form.email}
                  onChange={(v) => setForm((p) => (p ? { ...p, email: v } : p))}
                />
                <PhoneInput
                  tone="booking"
                  label={dict.phoneNumber}
                  value={form.phone_number}
                  onChange={(v) => setForm((p) => (p ? { ...p, phone_number: v } : p))}
                />
                <TextField
                  label={dict.streetAddress}
                  value={form.residence_address.street_address}
                  onChange={(v) => updateAddress("street_address", v)}
                />
                <TextField label={dict.zip} value={form.residence_address.zip} onChange={(v) => updateAddress("zip", v)} />
                <TextField label={dict.city} value={form.residence_address.city} onChange={(v) => updateAddress("city", v)} />
                <TextField
                  label={dict.stateOptional}
                  value={form.residence_address.state ?? ""}
                  onChange={(v) => updateAddress("state", v)}
                  required={false}
                />
                <TextField
                  label={dict.country}
                  value={form.residence_address.country}
                  onChange={(v) => updateAddress("country", v)}
                />
                <SelectField
                  label={dict.preferredLanguage}
                  value={form.preferred_language ?? ""}
                  noneLabel={dict.noPreference}
                  options={LANGUAGES}
                  onChange={(v) => setForm((p) => (p ? { ...p, preferred_language: (v || null) as Language | null } : p))}
                />
                <SelectField
                  label={dict.preferredCurrency}
                  value={form.preferred_currency ?? ""}
                  noneLabel={dict.noPreference}
                  options={CURRENCIES}
                  onChange={(v) => setForm((p) => (p ? { ...p, preferred_currency: (v || null) as Currency | null } : p))}
                />
              </div>

              {errorMessage && <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>}
              {saved && !errorMessage && <p className="text-sm text-teal-600 dark:text-teal-400">{dict.saved}</p>}

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={pending}
                  className="text-white font-semibold py-2.5 px-6 rounded-xl text-sm transition-all shadow-lg active:scale-[0.98] disabled:opacity-60 cursor-pointer"
                  style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
                >
                  {pending ? dict.saving : dict.save}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}

/* ── TextField ─────────────────────────────────────────── */
function TextField({
  label,
  value,
  onChange,
  type = "text",
  required = true,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
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
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-teal-300 focus:border-teal-400"
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
}: {
  label: string;
  value: string;
  options: string[];
  noneLabel: string;
  onChange: (v: string) => void;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
        {label}
      </label>
      <select
        id={id}
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
