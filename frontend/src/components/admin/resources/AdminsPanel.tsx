"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  createAdmin,
  deleteAdmin,
  listAdmins,
  updateAdmin,
  type Admin,
  type AdminInput,
} from "@/lib/api";
import { useAdminAuth } from "@/lib/admin-auth";
import { DataTable, type Column } from "../DataTable";
import { Modal } from "../Modal";
import { SubmitButton, TextField } from "../FormFields";

const emptyForm: AdminInput = { family_name: "", first_name: "", phone_number: "", email: "" };

export default function AdminsPanel() {
  const { session, logout } = useAdminAuth();
  const token = session!.token;

  const [admins, setAdmins] = useState<Admin[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [editing, setEditing] = useState<Admin | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<AdminInput>(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const load = () => {
    listAdmins(token)
      .then((data) => {
        setAdmins(data);
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

  const openEdit = (admin: Admin) => {
    setEditing(admin);
    setForm({
      family_name: admin.family_name,
      first_name: admin.first_name,
      phone_number: admin.phone_number,
      email: admin.email,
    });
    setFormError(null);
    setShowModal(true);
  };

  const handleDelete = async (admin: Admin) => {
    if (!window.confirm(`Delete admin ${admin.first_name} ${admin.family_name}?`)) return;
    try {
      await deleteAdmin(admin._id, token);
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      window.alert(err instanceof ApiError ? err.message : String(err));
    }
  };

  const handleBulkDelete = async (selectedAdmins: Admin[]) => {
    if (!window.confirm(`Delete ${selectedAdmins.length} admin${selectedAdmins.length === 1 ? "" : "s"}?`)) return;
    try {
      await Promise.all(selectedAdmins.map((a) => deleteAdmin(a._id, token)));
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
        await updateAdmin(editing._id, token, form);
      } else {
        await createAdmin(token, form);
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

  const columns: Column<Admin>[] = [
    { key: "name", label: "Name", render: (a) => `${a.first_name} ${a.family_name}` },
    { key: "email", label: "Email", render: (a) => a.email },
    { key: "phone", label: "Phone", render: (a) => a.phone_number },
  ];

  return (
    <div>
      <DataTable
        columns={columns}
        rows={admins}
        rowKey={(a) => a._id}
        onEdit={openEdit}
        onDelete={handleDelete}
        onBulkDelete={handleBulkDelete}
        onCreate={openCreate}
        createLabel="New admin"
        loading={loading}
        error={listError}
      />

      {showModal && (
        <Modal title={editing ? "Edit admin" : "New admin"} onClose={() => setShowModal(false)}>
          <form onSubmit={handleSubmit} className="space-y-4">
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
            {formError && <p className="text-sm text-red-600">{formError}</p>}
            <SubmitButton pending={pending} label={editing ? "Save changes" : "Create admin"} />
          </form>
        </Modal>
      )}
    </div>
  );
}
