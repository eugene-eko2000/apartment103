"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  createClosure,
  deleteClosure,
  listClosures,
  updateClosure,
  type Closure,
  type ClosureInput,
} from "@/lib/api";
import { useAdminAuth } from "@/lib/admin-auth";
import { DataTable, type Column } from "../DataTable";
import { Modal } from "../Modal";
import { SubmitButton, TextField } from "../FormFields";

const emptyForm: ClosureInput = { platform: "", begin_date: "", end_date: "" };

export default function ClosuresPanel() {
  const { session, logout } = useAdminAuth();
  const token = session!.token;

  const [closures, setClosures] = useState<Closure[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [editing, setEditing] = useState<Closure | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<ClosureInput>(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const load = () => {
    listClosures(token)
      .then((data) => {
        setClosures(data);
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

  const openEdit = (closure: Closure) => {
    setEditing(closure);
    setForm({ platform: closure.platform, begin_date: closure.begin_date, end_date: closure.end_date });
    setFormError(null);
    setShowModal(true);
  };

  const handleDelete = async (closure: Closure) => {
    if (!window.confirm(`Delete this ${closure.platform} closure?`)) return;
    try {
      await deleteClosure(closure._id, token);
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      window.alert(err instanceof ApiError ? err.message : String(err));
    }
  };

  const handleBulkDelete = async (selectedClosures: Closure[]) => {
    if (!window.confirm(`Delete ${selectedClosures.length} closure${selectedClosures.length === 1 ? "" : "s"}?`))
      return;
    try {
      await Promise.all(selectedClosures.map((c) => deleteClosure(c._id, token)));
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
        await updateClosure(editing._id, token, form);
      } else {
        await createClosure(token, form);
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

  const columns: Column<Closure>[] = [
    { key: "platform", label: "Platform", render: (c) => c.platform },
    { key: "begin_date", label: "Begin date", render: (c) => c.begin_date },
    { key: "end_date", label: "End date", render: (c) => c.end_date },
  ];

  return (
    <div>
      <DataTable
        columns={columns}
        rows={closures}
        rowKey={(c) => c._id}
        onEdit={openEdit}
        onDelete={handleDelete}
        onBulkDelete={handleBulkDelete}
        onCreate={openCreate}
        createLabel="New closure"
        loading={loading}
        error={listError}
        emptyLabel="No closures yet."
      />

      {showModal && (
        <Modal title={editing ? "Edit closure" : "New closure"} onClose={() => setShowModal(false)}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <TextField
              label="Platform"
              value={form.platform}
              placeholder="e.g. Airbnb, Booking.com"
              onChange={(v) => setForm((p) => ({ ...p, platform: v }))}
            />
            <TextField
              label="Begin date"
              type="date"
              value={form.begin_date}
              onChange={(v) => setForm((p) => ({ ...p, begin_date: v }))}
            />
            <TextField
              label="End date"
              type="date"
              value={form.end_date}
              onChange={(v) => setForm((p) => ({ ...p, end_date: v }))}
            />
            {formError && <p className="text-sm text-red-600 dark:text-red-400">{formError}</p>}
            <SubmitButton pending={pending} label={editing ? "Save changes" : "Create closure"} />
          </form>
        </Modal>
      )}
    </div>
  );
}
