"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  createPlan,
  deletePlan,
  listCancellationPolicies,
  listPlans,
  updatePlan,
  type CancellationPolicy,
  type Plan,
  type PlanInput,
} from "@/lib/api";
import { useAdminAuth } from "@/lib/admin-auth";
import { DataTable, type Column } from "../DataTable";
import { Modal } from "../Modal";
import { NumberField, SelectField, SubmitButton, TextField } from "../FormFields";

function emptyForm(defaultPolicyId: string): PlanInput {
  return {
    name: "",
    cancellation_policy_id: defaultPolicyId,
    price_ratio: 1,
  };
}

export default function PlansPanel() {
  const { session, logout } = useAdminAuth();
  const token = session!.token;

  const [plans, setPlans] = useState<Plan[]>([]);
  const [policies, setPolicies] = useState<CancellationPolicy[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [editing, setEditing] = useState<Plan | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<PlanInput>(emptyForm(""));
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const load = () => {
    Promise.all([listPlans(token), listCancellationPolicies(token)])
      .then(([planList, policyList]) => {
        setPlans(planList);
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

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm(policies[0]?._id ?? ""));
    setFormError(null);
    setShowModal(true);
  };

  const openEdit = (plan: Plan) => {
    setEditing(plan);
    setForm({
      name: plan.name,
      cancellation_policy_id: plan.cancellation_policy.id,
      price_ratio: plan.price_ratio,
    });
    setFormError(null);
    setShowModal(true);
  };

  const handleDelete = async (plan: Plan) => {
    if (!window.confirm(`Delete plan "${plan.name}"?`)) return;
    try {
      await deletePlan(plan._id, token);
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      window.alert(err instanceof ApiError ? err.message : String(err));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.cancellation_policy_id) {
      setFormError("Create a cancellation policy first.");
      return;
    }
    setPending(true);
    setFormError(null);
    try {
      if (editing) {
        await updatePlan(editing._id, token, form);
      } else {
        await createPlan(token, form);
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

  const columns: Column<Plan>[] = [
    { key: "name", label: "Name", render: (p) => p.name },
    { key: "ratio", label: "Price ratio", render: (p) => p.price_ratio.toFixed(2) },
    { key: "policy", label: "Cancellation policy", render: (p) => p.cancellation_policy.name },
  ];

  return (
    <div>
      <DataTable
        columns={columns}
        rows={plans}
        rowKey={(p) => p._id}
        onEdit={openEdit}
        onDelete={handleDelete}
        onCreate={openCreate}
        createLabel="New plan"
        loading={loading}
        error={listError}
      />

      {showModal && (
        <Modal title={editing ? "Edit plan" : "New plan"} onClose={() => setShowModal(false)}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <TextField label="Name" value={form.name} onChange={(v) => setForm((p) => ({ ...p, name: v }))} />
            <SelectField
              label="Cancellation policy"
              value={form.cancellation_policy_id}
              options={policies.map((p) => ({ value: p._id, label: p.name }))}
              onChange={(v) => setForm((p) => ({ ...p, cancellation_policy_id: v }))}
            />
            <NumberField
              label="Price ratio"
              value={form.price_ratio}
              min={0}
              step={0.01}
              onChange={(v) => setForm((p) => ({ ...p, price_ratio: v }))}
            />
            {formError && <p className="text-sm text-red-600">{formError}</p>}
            <SubmitButton pending={pending} label={editing ? "Save changes" : "Create plan"} />
          </form>
        </Modal>
      )}
    </div>
  );
}
