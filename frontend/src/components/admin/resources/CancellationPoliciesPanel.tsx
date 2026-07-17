"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  createCancellationPolicy,
  deleteCancellationPolicy,
  listCancellationPolicies,
  updateCancellationPolicy,
  type CancellationPolicy,
  type CancellationPolicyInput,
  type CancellationRule,
} from "@/lib/api";
import { useAdminAuth } from "@/lib/admin-auth";
import { DataTable, type Column } from "../DataTable";
import { Modal } from "../Modal";
import { NumberField, SubmitButton, TextField } from "../FormFields";
import { RepeatingRows } from "../RepeatingRows";

const emptyForm: CancellationPolicyInput = { name: "", rules: [] };
const emptyRule = (): CancellationRule => ({ days_before_checkin: 0, refund_percentage: 1 });

export default function CancellationPoliciesPanel() {
  const { session, logout } = useAdminAuth();
  const token = session!.token;

  const [policies, setPolicies] = useState<CancellationPolicy[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [editing, setEditing] = useState<CancellationPolicy | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<CancellationPolicyInput>(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const load = () => {
    listCancellationPolicies(token)
      .then((data) => {
        setPolicies(data);
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

  const openEdit = (policy: CancellationPolicy) => {
    setEditing(policy);
    setForm({ name: policy.name, rules: policy.rules });
    setFormError(null);
    setShowModal(true);
  };

  const handleDelete = async (policy: CancellationPolicy) => {
    if (!window.confirm(`Delete cancellation policy "${policy.name}"?`)) return;
    try {
      await deleteCancellationPolicy(policy._id, token);
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
        await updateCancellationPolicy(editing._id, token, form);
      } else {
        await createCancellationPolicy(token, form);
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

  const columns: Column<CancellationPolicy>[] = [
    { key: "name", label: "Name", render: (p) => p.name },
    { key: "rules", label: "Rules", render: (p) => `${p.rules.length} rule${p.rules.length === 1 ? "" : "s"}` },
  ];

  return (
    <div>
      <DataTable
        columns={columns}
        rows={policies}
        rowKey={(p) => p._id}
        onEdit={openEdit}
        onDelete={handleDelete}
        onCreate={openCreate}
        createLabel="New policy"
        loading={loading}
        error={listError}
      />

      {showModal && (
        <Modal title={editing ? "Edit cancellation policy" : "New cancellation policy"} onClose={() => setShowModal(false)}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <TextField label="Name" value={form.name} onChange={(v) => setForm((p) => ({ ...p, name: v }))} />
            <RepeatingRows<CancellationRule>
              label="Refund rules"
              items={form.rules}
              onChange={(rules) => setForm((p) => ({ ...p, rules }))}
              emptyRow={emptyRule}
              addLabel="Add rule"
              renderRow={(rule, update) => (
                <>
                  <NumberField
                    label="Days before check-in"
                    value={rule.days_before_checkin}
                    min={0}
                    step={1}
                    onChange={(v) => update({ days_before_checkin: v })}
                  />
                  <NumberField
                    label="Refund % (0-1)"
                    value={rule.refund_percentage}
                    min={0}
                    max={1}
                    step={0.05}
                    onChange={(v) => update({ refund_percentage: v })}
                  />
                </>
              )}
            />
            {formError && <p className="text-sm text-red-600">{formError}</p>}
            <SubmitButton pending={pending} label={editing ? "Save changes" : "Create policy"} />
          </form>
        </Modal>
      )}
    </div>
  );
}
