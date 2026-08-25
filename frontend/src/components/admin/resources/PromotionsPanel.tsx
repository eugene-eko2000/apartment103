"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  createPromotion,
  deletePromotion,
  listPromotions,
  updatePromotion,
  type Currency,
  type DiscountType,
  type Promotion,
  type PromotionInput,
} from "@/lib/api";
import { useAdminAuth } from "@/lib/admin-auth";
import { DataTable, type Column } from "../DataTable";
import { Modal } from "../Modal";
import { NumberField, SelectField, SubmitButton, TextField } from "../FormFields";
import { DateRangeCalendarField } from "../DateRangeCalendarField";

const CURRENCIES: Currency[] = ["EUR", "CHF", "USD", "GBP"];

const DISCOUNT_TYPES: { value: DiscountType; label: string }[] = [
  { value: "percent", label: "Percentage off" },
  { value: "amount", label: "Fixed amount off per night" },
];

const emptyForm: PromotionInput = {
  name: "",
  begin_date: "",
  end_date: "",
  discount_type: "percent",
  discount_ratio: 0,
  discount_amount: 0,
  currency: "CHF",
  min_stay_days: 1,
  active: true,
};

// The API stores the discount as a fraction (0.2 = 20% off); the form shows
// whole percent, which is what an admin thinks in.
const toPercent = (ratio: number) => Math.round(ratio * 1000) / 10;
const fromPercent = (percent: number) => percent / 100;

function describeDiscount(promotion: Promotion): string {
  return promotion.discount_type === "percent"
    ? `${toPercent(promotion.discount_ratio)} %`
    : `${promotion.currency} ${promotion.discount_amount.toFixed(2)} / night`;
}

export default function PromotionsPanel() {
  const { session, logout } = useAdminAuth();
  const token = session!.token;

  const [promotions, setPromotions] = useState<Promotion[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [editing, setEditing] = useState<Promotion | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<PromotionInput>(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const load = () => {
    listPromotions(token)
      .then((data) => {
        setPromotions(data);
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

  const openEdit = (promotion: Promotion) => {
    setEditing(promotion);
    setForm({
      name: promotion.name,
      begin_date: promotion.begin_date,
      end_date: promotion.end_date,
      discount_type: promotion.discount_type,
      discount_ratio: promotion.discount_ratio,
      discount_amount: promotion.discount_amount,
      currency: promotion.currency,
      min_stay_days: promotion.min_stay_days,
      active: promotion.active,
    });
    setFormError(null);
    setShowModal(true);
  };

  // Bookings snapshot the promotions they were made under (by value, never
  // a reference), so removing an offer only stops it applying to *new*
  // bookings — worth saying out loud, since "delete" usually implies undoing
  // something.
  const deleteWarning = (count: number) =>
    `Delete ${count === 1 ? "this promotion" : `${count} promotions`}? Bookings already made keep the discount they were priced with — their stored snapshot governs, not this record.`;

  const handleDelete = async (promotion: Promotion) => {
    if (!window.confirm(deleteWarning(1))) return;
    try {
      await deletePromotion(promotion._id, token);
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      window.alert(err instanceof ApiError ? err.message : String(err));
    }
  };

  const handleBulkDelete = async (selected: Promotion[]) => {
    if (!window.confirm(deleteWarning(selected.length))) return;
    try {
      await Promise.all(selected.map((p) => deletePromotion(p._id, token)));
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      window.alert(err instanceof ApiError ? err.message : String(err));
    }
  };

  // The backend validates all of this too — these guards just turn a 422
  // into a message next to the field that caused it.
  const validate = (): string | null => {
    if (!form.begin_date || !form.end_date) return "Select the promotion's date range.";
    if (form.end_date < form.begin_date) return "The end date must not be before the begin date.";
    if (form.discount_type === "percent" && form.discount_ratio <= 0)
      return "Enter a discount percentage above 0.";
    if (form.discount_type === "amount" && form.discount_amount <= 0)
      return "Enter a discount amount above 0.";
    return null;
  };

  const handleSubmit = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    const invalid = validate();
    if (invalid) {
      setFormError(invalid);
      return;
    }
    setPending(true);
    setFormError(null);
    try {
      if (editing) {
        await updatePromotion(editing._id, token, form);
      } else {
        await createPromotion(token, form);
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

  const columns: Column<Promotion>[] = [
    { key: "name", label: "Name", render: (p) => p.name },
    { key: "dates", label: "Dates", render: (p) => `${p.begin_date} – ${p.end_date}` },
    { key: "discount", label: "Discount", render: (p) => describeDiscount(p) },
    { key: "min_stay", label: "Min stay", render: (p) => `${p.min_stay_days} night${p.min_stay_days === 1 ? "" : "s"}` },
    {
      key: "active",
      label: "Active",
      render: (p) => (
        <span
          className={`inline-flex px-2 py-0.5 rounded-full text-xs font-semibold ${
            p.active
              ? "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300"
              : "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300"
          }`}
        >
          {p.active ? "Active" : "Parked"}
        </span>
      ),
    },
  ];

  return (
    <div>
      <DataTable
        columns={columns}
        rows={promotions}
        rowKey={(p) => p._id}
        onEdit={openEdit}
        onDelete={handleDelete}
        onBulkDelete={handleBulkDelete}
        onCreate={openCreate}
        createLabel="New promotion"
        loading={loading}
        error={listError}
        emptyLabel="No promotions yet."
      />

      {showModal && (
        <Modal
          title={editing ? "Edit promotion" : "New promotion"}
          onClose={() => setShowModal(false)}
          footer={
            <SubmitButton
              form="promotion-form"
              pending={pending}
              label={editing ? "Save changes" : "Create promotion"}
            />
          }
        >
          <form id="promotion-form" onSubmit={handleSubmit} className="space-y-4">
            <TextField
              label="Name"
              value={form.name}
              placeholder="e.g. Spring escape"
              onChange={(v) => setForm((p) => ({ ...p, name: v }))}
            />
            {/* blockedRanges is empty on purpose: promotions may overlap
                each other — the largest discount wins per night (see
                backend/app/services/booking_pricing.py). */}
            <DateRangeCalendarField
              label="Promotion dates (end date inclusive)"
              beginDate={form.begin_date}
              endDate={form.end_date}
              blockedRanges={[]}
              onChange={(begin_date, end_date) => setForm((p) => ({ ...p, begin_date, end_date }))}
            />
            <SelectField
              label="Discount type"
              value={form.discount_type}
              options={DISCOUNT_TYPES}
              onChange={(v) => setForm((p) => ({ ...p, discount_type: v }))}
            />
            {form.discount_type === "percent" ? (
              <NumberField
                label="Discount %"
                value={toPercent(form.discount_ratio)}
                min={0}
                max={100}
                step={0.1}
                onChange={(v) => setForm((p) => ({ ...p, discount_ratio: fromPercent(v) }))}
              />
            ) : (
              <div className="grid grid-cols-2 gap-3">
                <NumberField
                  label="Discount amount (per night)"
                  value={form.discount_amount}
                  min={0}
                  step={0.01}
                  onChange={(v) => setForm((p) => ({ ...p, discount_amount: v }))}
                />
                <SelectField
                  label="Currency"
                  value={form.currency}
                  options={CURRENCIES.map((c) => ({ value: c, label: c }))}
                  onChange={(v) => setForm((p) => ({ ...p, currency: v }))}
                />
              </div>
            )}
            <NumberField
              label="Minimum stay (nights)"
              value={form.min_stay_days}
              min={1}
              step={1}
              onChange={(v) => setForm((p) => ({ ...p, min_stay_days: v }))}
            />
            <p className="text-xs text-slate-400 dark:text-slate-500 -mt-2">
              Gates the discount only — a shorter stay is still bookable, at the full rate.
            </p>
            <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={form.active}
                onChange={(e) => setForm((p) => ({ ...p, active: e.target.checked }))}
                className="rounded border-slate-300 dark:border-slate-600 cursor-pointer"
              />
              Active
              <span className="text-xs text-slate-400 dark:text-slate-500">
                (park an offer here instead of deleting it)
              </span>
            </label>
            {formError && <p className="text-sm text-red-600 dark:text-red-400">{formError}</p>}
          </form>
        </Modal>
      )}
    </div>
  );
}
