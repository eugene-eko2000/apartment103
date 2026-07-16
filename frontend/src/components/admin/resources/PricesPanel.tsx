"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  createPrice,
  deletePrice,
  listPrices,
  updatePrice,
  type Currency,
  type DateRangeRate,
  type Price,
  type PriceInput,
} from "@/lib/api";
import { useAdminAuth } from "@/lib/admin-auth";
import { DataTable, type Column } from "../DataTable";
import { Modal } from "../Modal";
import { NumberField, SelectField, SubmitButton, TextField } from "../FormFields";
import { RepeatingRows } from "../RepeatingRows";

const CURRENCIES: Currency[] = ["EUR", "CHF", "USD", "GBP"];

const emptyDateRange = (): DateRangeRate => ({ begin_date: "", end_date: "", daily_rate: 0 });

const emptyForm = (): PriceInput => ({
  period: {
    begin_date: "",
    end_date: "",
    currency: "CHF",
    date_ranges: [],
  },
});

export default function PricesPanel() {
  const { session, logout } = useAdminAuth();
  const token = session!.token;

  const [prices, setPrices] = useState<Price[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [editing, setEditing] = useState<Price | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<PriceInput>(emptyForm());
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const load = () => {
    listPrices(token)
      .then((data) => {
        setPrices(data);
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
    setForm(emptyForm());
    setFormError(null);
    setShowModal(true);
  };

  const openEdit = (price: Price) => {
    setEditing(price);
    setForm({ period: price.period });
    setFormError(null);
    setShowModal(true);
  };

  const handleDelete = async (price: Price) => {
    if (!window.confirm(`Delete price period "${price.period.begin_date} – ${price.period.end_date}"?`)) return;
    try {
      await deletePrice(price._id, token);
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      window.alert(err instanceof ApiError ? err.message : String(err));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setPending(true);
    setFormError(null);
    try {
      if (editing) {
        await updatePrice(editing._id, token, form);
      } else {
        await createPrice(token, form);
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

  const columns: Column<Price>[] = [
    { key: "range", label: "Period", render: (p) => `${p.period.begin_date} – ${p.period.end_date}` },
    { key: "currency", label: "Currency", render: (p) => p.period.currency },
    { key: "ranges", label: "Date ranges", render: (p) => `${p.period.date_ranges.length}` },
  ];

  return (
    <div>
      <DataTable
        columns={columns}
        rows={prices}
        rowKey={(p) => p._id}
        onEdit={openEdit}
        onDelete={handleDelete}
        onCreate={openCreate}
        createLabel="New price period"
        loading={loading}
        error={listError}
      />

      {showModal && (
        <Modal title={editing ? "Edit price period" : "New price period"} onClose={() => setShowModal(false)}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <TextField
                label="Begin date"
                type="date"
                value={form.period.begin_date}
                onChange={(v) => setForm((p) => ({ ...p, period: { ...p.period, begin_date: v } }))}
              />
              <TextField
                label="End date"
                type="date"
                value={form.period.end_date}
                onChange={(v) => setForm((p) => ({ ...p, period: { ...p.period, end_date: v } }))}
              />
            </div>
            <SelectField
              label="Currency"
              value={form.period.currency}
              options={CURRENCIES.map((c) => ({ value: c, label: c }))}
              onChange={(v) => setForm((p) => ({ ...p, period: { ...p.period, currency: v } }))}
            />
            <RepeatingRows<DateRangeRate>
              label="Daily rates"
              items={form.period.date_ranges}
              onChange={(date_ranges) => setForm((p) => ({ ...p, period: { ...p.period, date_ranges } }))}
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
                  <NumberField
                    label="Daily rate"
                    value={range.daily_rate}
                    min={0}
                    step={0.01}
                    onChange={(v) => update({ daily_rate: v })}
                  />
                </>
              )}
            />
            {formError && <p className="text-sm text-red-600">{formError}</p>}
            <SubmitButton pending={pending} label={editing ? "Save changes" : "Create price period"} />
          </form>
        </Modal>
      )}
    </div>
  );
}
