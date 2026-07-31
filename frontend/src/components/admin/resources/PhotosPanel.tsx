"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  addImageLabel,
  deleteImage,
  imageUrl,
  listImages,
  removeImageLabel,
  uploadImage,
  type ImageAsset,
  type ImageCategory,
} from "@/lib/api";
import { useAdminAuth } from "@/lib/admin-auth";
import { CATEGORIES, categoryLabel } from "@/lib/imageCategories";
import { Modal } from "../Modal";
import { FileField, NumberField, SelectField, SubmitButton, TextField } from "../FormFields";
import GooglePhotosImportModal from "./GooglePhotosImportModal";

const GOOGLE_PHOTOS_ENABLED = Boolean(process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID);

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}

export default function PhotosPanel() {
  const { session, logout } = useAdminAuth();
  const token = session!.token;

  const [images, setImages] = useState<ImageAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<ImageCategory | "">("");

  const [showUpload, setShowUpload] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploadCategory, setUploadCategory] = useState<ImageCategory>("hero");
  const [alt, setAlt] = useState("");
  const [sortOrder, setSortOrder] = useState(0);
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const [viewing, setViewing] = useState<ImageAsset | null>(null);
  const [showGoogleImport, setShowGoogleImport] = useState(false);

  const [labelInput, setLabelInput] = useState("");
  const [labelPending, setLabelPending] = useState(false);
  const [labelError, setLabelError] = useState<string | null>(null);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkPending, setBulkPending] = useState(false);
  const [showBulkLabels, setShowBulkLabels] = useState(false);
  const [bulkLabelInput, setBulkLabelInput] = useState("");
  const [bulkLabelError, setBulkLabelError] = useState<string | null>(null);

  const knownLabels = useMemo(() => Array.from(new Set(images.flatMap((i) => i.labels))).sort(), [images]);

  // Ids can linger in `selected` after their image disappears (reload,
  // filter change, deletion) — filter against the current list here rather
  // than pruning state in an effect.
  const effectiveSelected = useMemo(() => {
    const validIds = new Set(images.map((i) => i._id));
    const next = new Set<string>();
    selected.forEach((id) => {
      if (validIds.has(id)) next.add(id);
    });
    return next;
  }, [selected, images]);

  const selectedImages = useMemo(
    () => images.filter((i) => effectiveSelected.has(i._id)),
    [images, effectiveSelected]
  );

  const bulkLabels = useMemo(
    () => Array.from(new Set(selectedImages.flatMap((i) => i.labels))).sort(),
    [selectedImages]
  );

  const load = () => {
    listImages(categoryFilter || undefined)
      .then((data) => {
        setImages(data);
        setListError(null);
      })
      .catch((err) => setListError(err instanceof ApiError ? err.message : String(err)))
      .finally(() => setLoading(false));
  };

  useEffect(load, [categoryFilter]);

  const openUpload = () => {
    setFile(null);
    setUploadCategory((categoryFilter as ImageCategory) || "hero");
    setAlt("");
    setSortOrder(0);
    setFormError(null);
    setShowUpload(true);
  };

  const handleUpload = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!file) return;
    setPending(true);
    setFormError(null);
    try {
      await uploadImage(token, file, { category: uploadCategory, alt, sort_order: sortOrder });
      setShowUpload(false);
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      setFormError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setPending(false);
    }
  };

  const handleDelete = async (image: ImageAsset) => {
    if (!window.confirm(`Delete this photo${image.alt ? ` ("${image.alt}")` : ""}?`)) return;
    try {
      await deleteImage(image._id, token);
      if (viewing?._id === image._id) setViewing(null);
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      window.alert(err instanceof ApiError ? err.message : String(err));
    }
  };

  const handleAddLabel = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!viewing || !labelInput.trim()) return;
    setLabelPending(true);
    setLabelError(null);
    try {
      const updated = await addImageLabel(viewing._id, token, labelInput.trim());
      setViewing(updated);
      setLabelInput("");
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      setLabelError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setLabelPending(false);
    }
  };

  const handleRemoveLabel = async (label: string) => {
    if (!viewing) return;
    try {
      const updated = await removeImageLabel(viewing._id, token, label);
      setViewing(updated);
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      window.alert(err instanceof ApiError ? err.message : String(err));
    }
  };

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleBulkDelete = async () => {
    if (selectedImages.length === 0) return;
    if (!window.confirm(`Delete ${selectedImages.length} photo${selectedImages.length === 1 ? "" : "s"}?`)) return;
    setBulkPending(true);
    try {
      await Promise.all(selectedImages.map((img) => deleteImage(img._id, token)));
      setSelected(new Set());
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      window.alert(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBulkPending(false);
    }
  };

  const handleBulkAddLabel = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!bulkLabelInput.trim() || selectedImages.length === 0) return;
    setBulkPending(true);
    setBulkLabelError(null);
    try {
      await Promise.all(selectedImages.map((img) => addImageLabel(img._id, token, bulkLabelInput.trim())));
      setBulkLabelInput("");
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      setBulkLabelError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBulkPending(false);
    }
  };

  const handleBulkRemoveLabel = async (label: string) => {
    if (selectedImages.length === 0) return;
    setBulkPending(true);
    try {
      await Promise.all(selectedImages.map((img) => removeImageLabel(img._id, token, label)));
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      window.alert(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBulkPending(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4 gap-3">
        <div className="w-56">
          <SelectField
            label="Category"
            value={categoryFilter}
            options={CATEGORIES}
            noneLabel="All categories"
            onChange={(v) => setCategoryFilter(v as ImageCategory | "")}
          />
        </div>
        <div className="flex gap-2 self-end">
          {GOOGLE_PHOTOS_ENABLED && (
            <button
              type="button"
              onClick={() => setShowGoogleImport(true)}
              className="bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200 text-sm font-semibold px-4 py-2 rounded-lg cursor-pointer transition-colors hover:bg-slate-50 dark:hover:bg-slate-700"
            >
              Import from Google Photos
            </button>
          )}
          <button
            type="button"
            onClick={openUpload}
            className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-4 py-2 rounded-lg cursor-pointer transition-colors"
          >
            + Add photo
          </button>
        </div>
      </div>

      <datalist id="known-labels">
        {knownLabels.map((l) => (
          <option key={l} value={l} />
        ))}
      </datalist>

      {effectiveSelected.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 mb-4 px-3 py-2 bg-indigo-50 dark:bg-indigo-900/30 border border-indigo-200 dark:border-indigo-800 rounded-lg">
          <span className="text-sm text-indigo-800 dark:text-indigo-300 font-medium">
            {effectiveSelected.size} selected
          </span>
          {effectiveSelected.size < images.length && (
            <button
              type="button"
              onClick={() => setSelected(new Set(images.map((i) => i._id)))}
              className="text-sm font-medium text-indigo-700 dark:text-indigo-300 hover:underline cursor-pointer"
            >
              Select all {images.length}
            </button>
          )}
          <button
            type="button"
            onClick={() => setShowBulkLabels(true)}
            disabled={bulkPending}
            className="text-sm font-semibold text-indigo-700 dark:text-indigo-300 hover:underline cursor-pointer disabled:opacity-50"
          >
            Manage labels
          </button>
          <button
            type="button"
            onClick={handleBulkDelete}
            disabled={bulkPending}
            className="text-sm font-semibold text-red-600 dark:text-red-400 hover:underline cursor-pointer disabled:opacity-50"
          >
            Delete selected
          </button>
          <button
            type="button"
            onClick={() => setSelected(new Set())}
            className="text-sm text-slate-500 dark:text-slate-400 hover:underline cursor-pointer ml-auto"
          >
            Clear
          </button>
        </div>
      )}

      {listError && <p className="text-sm text-red-600 dark:text-red-400 mb-3">{listError}</p>}

      {loading && <p className="text-center text-slate-400 dark:text-slate-500 py-6">Loading…</p>}

      {!loading && images.length === 0 && !listError && (
        <p className="text-center text-slate-400 dark:text-slate-500 py-6 border border-dashed border-slate-300 dark:border-slate-700 rounded-lg">
          No photos yet.
        </p>
      )}

      {!loading && images.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {images.map((image) => (
            <div
              key={image._id}
              className={`group relative border rounded-lg overflow-hidden bg-white dark:bg-slate-800 ${
                effectiveSelected.has(image._id)
                  ? "ring-2 ring-indigo-500 border-transparent"
                  : "border-slate-200 dark:border-slate-700"
              }`}
            >
              <label
                className={`absolute top-2 left-2 z-10 flex items-center justify-center w-6 h-6 rounded-full cursor-pointer transition-all ${
                  effectiveSelected.has(image._id)
                    ? "bg-indigo-600 border-2 border-indigo-600 opacity-100"
                    : "bg-black/20 border-2 border-white opacity-0 group-hover:opacity-100"
                }`}
                aria-label="Select photo"
              >
                <input
                  type="checkbox"
                  checked={effectiveSelected.has(image._id)}
                  onChange={() => toggleSelect(image._id)}
                  className="sr-only"
                />
                {effectiveSelected.has(image._id) && (
                  <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5 text-white" aria-hidden="true">
                    <path
                      fillRule="evenodd"
                      d="M16.704 5.29a1 1 0 010 1.415l-7.5 7.5a1 1 0 01-1.415 0l-3.5-3.5a1 1 0 111.415-1.415L8.5 12.086l6.79-6.795a1 1 0 011.414 0z"
                      clipRule="evenodd"
                    />
                  </svg>
                )}
              </label>
              <button
                type="button"
                onClick={() => {
                  setViewing(image);
                  setLabelInput("");
                  setLabelError(null);
                }}
                className="block w-full aspect-square cursor-pointer"
                aria-label="View photo"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={imageUrl(image.key)}
                  alt={image.alt}
                  className="w-full h-full object-cover"
                />
              </button>
              <div className="p-2">
                <span className="inline-block text-[11px] font-medium text-indigo-700 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/40 px-1.5 py-0.5 rounded">
                  {categoryLabel(image.category)}
                </span>
                {image.alt && (
                  <p className="text-xs text-slate-600 dark:text-slate-300 mt-1 truncate" title={image.alt}>
                    {image.alt}
                  </p>
                )}
                {image.labels.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {image.labels.map((label) => (
                      <span
                        key={label}
                        className="text-[10px] font-medium bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-300 px-1.5 py-0.5 rounded"
                      >
                        {label}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={() => handleDelete(image)}
                aria-label="Delete photo"
                className="absolute top-1.5 right-1.5 bg-black/60 hover:bg-red-600 text-white text-xs font-medium w-7 h-7 rounded-full opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer flex items-center justify-center"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      {showUpload && (
        <Modal title="Add photo" onClose={() => setShowUpload(false)}>
          <form onSubmit={handleUpload} className="space-y-4">
            <FileField
              label="File"
              accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif"
              onChange={setFile}
            />
            <SelectField
              label="Category"
              value={uploadCategory}
              options={CATEGORIES}
              onChange={(v) => setUploadCategory(v as ImageCategory)}
            />
            <TextField label="Alt text" value={alt} required={false} onChange={setAlt} placeholder="Describe the photo" />
            <NumberField label="Sort order" value={sortOrder} onChange={setSortOrder} step={1} required={false} />
            {formError && <p className="text-sm text-red-600 dark:text-red-400">{formError}</p>}
            <SubmitButton pending={pending} label="Upload" />
          </form>
        </Modal>
      )}

      {viewing && (
        <Modal title={categoryLabel(viewing.category)} onClose={() => setViewing(null)} maxHeight="calc(100vh - 120px)">
          <div className="space-y-4">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={imageUrl(viewing.key)} alt={viewing.alt} className="w-full rounded-lg" />
            <dl className="text-sm text-slate-600 dark:text-slate-300 grid grid-cols-2 gap-x-4 gap-y-1">
              {viewing.alt && (
                <>
                  <dt className="text-slate-400 dark:text-slate-500">Alt text</dt>
                  <dd className="col-span-1">{viewing.alt}</dd>
                </>
              )}
              <dt className="text-slate-400 dark:text-slate-500">Dimensions</dt>
              <dd>{viewing.width && viewing.height ? `${viewing.width} × ${viewing.height}` : "—"}</dd>
              <dt className="text-slate-400 dark:text-slate-500">Size</dt>
              <dd>{formatBytes(viewing.size_bytes)}</dd>
              <dt className="text-slate-400 dark:text-slate-500">Uploaded</dt>
              <dd>{new Date(viewing.uploaded_at).toLocaleString()}</dd>
            </dl>

            <div>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">
                Labels — stable aliases the frontend can look up by name (e.g. &quot;hero-current&quot;), instead
                of a specific photo. Move a label to a new photo by adding it there and removing it here.
              </p>
              <div className="flex flex-wrap gap-1.5 mb-2">
                {viewing.labels.length === 0 && (
                  <span className="text-xs text-slate-400 dark:text-slate-500">No labels</span>
                )}
                {viewing.labels.map((label) => (
                  <span
                    key={label}
                    className="inline-flex items-center gap-1 text-xs font-medium bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 pl-2 pr-1 py-1 rounded-full"
                  >
                    {label}
                    <button
                      type="button"
                      onClick={() => handleRemoveLabel(label)}
                      aria-label={`Remove label ${label}`}
                      className="text-slate-400 hover:text-red-600 dark:hover:text-red-400 cursor-pointer leading-none"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
              <form onSubmit={handleAddLabel} className="flex gap-2">
                <input
                  list="known-labels"
                  value={labelInput}
                  onChange={(e) => setLabelInput(e.target.value)}
                  placeholder="Add label…"
                  className="flex-1 min-w-0 px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-400 focus:border-indigo-500"
                />
                <button
                  type="submit"
                  disabled={labelPending || !labelInput.trim()}
                  className="bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-semibold px-3 py-1.5 rounded-lg cursor-pointer disabled:opacity-50 transition-colors"
                >
                  Add
                </button>
              </form>
              {labelError && <p className="text-xs text-red-600 dark:text-red-400 mt-1">{labelError}</p>}
            </div>

            <button
              type="button"
              onClick={() => handleDelete(viewing)}
              className="w-full bg-red-600 hover:bg-red-700 text-white text-sm font-semibold py-2.5 rounded-lg cursor-pointer transition-colors"
            >
              Delete photo
            </button>
          </div>
        </Modal>
      )}

      {showBulkLabels && (
        <Modal
          title={`Manage labels — ${effectiveSelected.size} photo${effectiveSelected.size === 1 ? "" : "s"}`}
          onClose={() => setShowBulkLabels(false)}
        >
          <div className="space-y-4">
            {bulkLabels.length > 0 && (
              <div>
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">
                  Remove a label (from every selected photo that has it)
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {bulkLabels.map((label) => (
                    <button
                      key={label}
                      type="button"
                      onClick={() => handleBulkRemoveLabel(label)}
                      disabled={bulkPending}
                      className="inline-flex items-center gap-1 text-xs font-medium bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 pl-2 pr-1 py-1 rounded-full hover:bg-red-50 dark:hover:bg-red-900/30 hover:text-red-700 dark:hover:text-red-300 cursor-pointer disabled:opacity-50 transition-colors"
                    >
                      {label} <span aria-hidden>×</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">
                Add a label to all selected
              </p>
              <form onSubmit={handleBulkAddLabel} className="flex gap-2">
                <input
                  list="known-labels"
                  value={bulkLabelInput}
                  onChange={(e) => setBulkLabelInput(e.target.value)}
                  placeholder="Add label…"
                  className="flex-1 min-w-0 px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-400 focus:border-indigo-500"
                />
                <button
                  type="submit"
                  disabled={bulkPending || !bulkLabelInput.trim()}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold px-3 py-1.5 rounded-lg cursor-pointer disabled:opacity-50 transition-colors"
                >
                  Add
                </button>
              </form>
              {bulkLabelError && <p className="text-xs text-red-600 dark:text-red-400 mt-1">{bulkLabelError}</p>}
            </div>
          </div>
        </Modal>
      )}

      {showGoogleImport && (
        <GooglePhotosImportModal
          defaultCategory={(categoryFilter as ImageCategory) || "hero"}
          onClose={() => setShowGoogleImport(false)}
          onImported={load}
        />
      )}
    </div>
  );
}
