"use client";

import { useState } from "react";
import { ApiError, createCategory, deleteCategory, updateCategory, type Category } from "@/lib/api";
import { Modal } from "../Modal";

function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
}

export default function CategoriesManageModal({
  categories,
  token,
  photoCountBySlug,
  onClose,
  onChanged,
  onUnauthorized,
}: {
  categories: Category[];
  token: string;
  photoCountBySlug: Record<string, number>;
  onClose: () => void;
  onChanged: () => void;
  onUnauthorized: () => void;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [addPending, setAddPending] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renamePending, setRenamePending] = useState(false);
  const [rowError, setRowError] = useState<Record<string, string>>({});
  const [deletePending, setDeletePending] = useState<string | null>(null);

  const handleNameChange = (v: string) => {
    setName(v);
    if (!slugEdited) setSlug(slugify(v));
  };

  const handleAdd = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!name.trim() || !slug.trim()) return;
    setAddPending(true);
    setAddError(null);
    try {
      await createCategory(token, { slug: slug.trim(), name: name.trim() });
      setName("");
      setSlug("");
      setSlugEdited(false);
      onChanged();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return onUnauthorized();
      setAddError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setAddPending(false);
    }
  };

  const startRename = (category: Category) => {
    setRenameId(category._id);
    setRenameValue(category.name);
  };

  const handleRename = async (e: React.SubmitEvent<HTMLFormElement>, category: Category) => {
    e.preventDefault();
    if (!renameValue.trim()) return;
    setRenamePending(true);
    setRowError((prev) => ({ ...prev, [category._id]: "" }));
    try {
      await updateCategory(category._id, token, { name: renameValue.trim() });
      setRenameId(null);
      onChanged();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return onUnauthorized();
      setRowError((prev) => ({
        ...prev,
        [category._id]: err instanceof ApiError ? err.message : String(err),
      }));
    } finally {
      setRenamePending(false);
    }
  };

  const handleDelete = async (category: Category) => {
    if (!window.confirm(`Delete category "${category.name}"?`)) return;
    setDeletePending(category._id);
    setRowError((prev) => ({ ...prev, [category._id]: "" }));
    try {
      await deleteCategory(category._id, token);
      onChanged();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return onUnauthorized();
      setRowError((prev) => ({
        ...prev,
        [category._id]: err instanceof ApiError ? err.message : String(err),
      }));
    } finally {
      setDeletePending(null);
    }
  };

  const footer = (
    <form onSubmit={handleAdd} className="space-y-2">
      <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Add a category</p>
      <div className="flex gap-2">
        <input
          value={name}
          onChange={(e) => handleNameChange(e.target.value)}
          placeholder="Name"
          className="flex-1 min-w-0 px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400"
        />
        <input
          value={slug}
          onChange={(e) => {
            setSlugEdited(true);
            setSlug(slugify(e.target.value));
          }}
          placeholder="slug"
          className="w-32 px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400"
        />
        <button
          type="submit"
          disabled={addPending || !name.trim() || !slug.trim()}
          className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-3 py-1.5 rounded-lg cursor-pointer disabled:opacity-50 transition-colors"
        >
          Add
        </button>
      </div>
      {addError && <p className="text-xs text-red-600 dark:text-red-400">{addError}</p>}
    </form>
  );

  return (
    <Modal title="Manage categories" onClose={onClose} footer={footer}>
      <div className="space-y-4">
        <ul className="space-y-2">
          {categories.map((category) => {
            const count = photoCountBySlug[category.slug] ?? 0;
            const isRenaming = renameId === category._id;
            return (
              <li
                key={category._id}
                className="border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2"
              >
                {isRenaming ? (
                  <form onSubmit={(e) => handleRename(e, category)} className="flex gap-2">
                    <input
                      autoFocus
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      className="flex-1 min-w-0 px-2 py-1 rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400"
                    />
                    <button
                      type="submit"
                      disabled={renamePending || !renameValue.trim()}
                      className="text-xs font-semibold text-indigo-700 dark:text-indigo-300 hover:underline cursor-pointer disabled:opacity-50"
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={() => setRenameId(null)}
                      className="text-xs text-slate-500 dark:text-slate-400 hover:underline cursor-pointer"
                    >
                      Cancel
                    </button>
                  </form>
                ) : (
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-800 dark:text-slate-100 truncate">
                        {category.name}
                      </p>
                      <p className="text-xs text-slate-400 dark:text-slate-500">
                        {category.slug} · {count} photo{count === 1 ? "" : "s"}
                      </p>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <button
                        type="button"
                        onClick={() => startRename(category)}
                        className="text-xs font-semibold text-indigo-700 dark:text-indigo-300 hover:underline cursor-pointer"
                      >
                        Rename
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(category)}
                        disabled={count > 0 || deletePending === category._id}
                        title={count > 0 ? "Only an empty category can be removed" : undefined}
                        className="text-xs font-semibold text-red-600 dark:text-red-400 hover:underline cursor-pointer disabled:opacity-40 disabled:hover:no-underline disabled:cursor-not-allowed"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                )}
                {rowError[category._id] && (
                  <p className="text-xs text-red-600 dark:text-red-400 mt-1">{rowError[category._id]}</p>
                )}
              </li>
            );
          })}
          {categories.length === 0 && (
            <li className="text-sm text-slate-400 dark:text-slate-500 py-2">No categories yet.</li>
          )}
        </ul>
      </div>
    </Modal>
  );
}
