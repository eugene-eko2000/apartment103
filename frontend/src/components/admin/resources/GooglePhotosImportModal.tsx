"use client";

import { useRef, useState } from "react";
import { ApiError, uploadImage, type ImageCategory } from "@/lib/api";
import { useAdminAuth } from "@/lib/admin-auth";
import {
  createPickerSession,
  deletePickerSession,
  downloadMediaItemFile,
  getGooglePhotosAccessToken,
  getPickerSession,
  isSupportedPhoto,
  listSessionMediaItems,
  parsePollIntervalMs,
  type PickedMediaItem,
  type PickerSession,
} from "@/lib/googlePhotos";
import { Modal } from "../Modal";
import { SelectField } from "../FormFields";
import { CATEGORIES } from "@/lib/imageCategories";

type Step = "category" | "connecting" | "waiting" | "importing" | "summary";

interface ImportResult {
  imported: number;
  skipped: number;
  failed: { filename: string; reason: string }[];
}

// Turns "sunset-over-the-lake.jpg" into "sunset over the lake" as a
// starting-point alt text — better than nothing, editable later by
// re-uploading if it's off (there's no metadata-edit endpoint, see
// backend/app/api/routes/images.py).
function altFromFilename(filename: string): string {
  return filename
    .replace(/\.[^.]+$/, "")
    .replace(/[-_]+/g, " ")
    .trim();
}

export default function GooglePhotosImportModal({
  defaultCategory,
  onClose,
  onImported,
}: {
  defaultCategory: ImageCategory;
  onClose: () => void;
  onImported: () => void;
}) {
  const { session, logout } = useAdminAuth();
  const token = session!.token;

  const [step, setStep] = useState<Step>("category");
  const [category, setCategory] = useState<ImageCategory>(defaultCategory);
  const [error, setError] = useState<string | null>(null);
  const [pickerUri, setPickerUri] = useState<string | null>(null);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [result, setResult] = useState<ImportResult | null>(null);

  const cancelledRef = useRef(false);
  const sessionIdRef = useRef<string | null>(null);
  const accessTokenRef = useRef<string | null>(null);

  const cleanupSession = async () => {
    if (sessionIdRef.current && accessTokenRef.current) {
      await deletePickerSession(accessTokenRef.current, sessionIdRef.current).catch(() => {});
      sessionIdRef.current = null;
    }
  };

  const handleCancel = async () => {
    cancelledRef.current = true;
    await cleanupSession();
    onClose();
  };

  const pollUntilReady = async (
    accessToken: string,
    sessionId: string,
    expireTime: string,
    pollIntervalMs: number
  ): Promise<PickerSession | null> => {
    const expiresAt = new Date(expireTime).getTime();
    while (!cancelledRef.current) {
      if (Date.now() > expiresAt) {
        throw new Error("The Google Photos selection window expired before any photos were chosen. Please try again.");
      }
      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
      if (cancelledRef.current) return null;
      const current = await getPickerSession(accessToken, sessionId);
      if (current.mediaItemsSet) return current;
    }
    return null;
  };

  const runImport = async (accessToken: string, items: PickedMediaItem[]) => {
    const supported = items.filter(isSupportedPhoto);
    const skipped = items.length - supported.length;
    setStep("importing");
    setProgress({ done: 0, total: supported.length });

    const failed: { filename: string; reason: string }[] = [];
    let imported = 0;

    for (const item of supported) {
      if (cancelledRef.current) break;
      try {
        const file = await downloadMediaItemFile(accessToken, item);
        await uploadImage(token, file, { category, alt: altFromFilename(item.mediaFile.filename), sort_order: 0 });
        imported += 1;
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          logout();
          return;
        }
        failed.push({
          filename: item.mediaFile.filename,
          reason: err instanceof Error ? err.message : String(err),
        });
      }
      setProgress((p) => ({ ...p, done: p.done + 1 }));
    }

    await cleanupSession();
    if (cancelledRef.current) {
      onClose();
      return;
    }
    setResult({ imported, skipped, failed });
    setStep("summary");
    onImported();
  };

  const handleConnect = async () => {
    setError(null);
    setStep("connecting");
    try {
      const accessToken = await getGooglePhotosAccessToken();
      accessTokenRef.current = accessToken;

      const pickerSession = await createPickerSession(accessToken);
      sessionIdRef.current = pickerSession.id;
      setPickerUri(pickerSession.pickerUri);
      setStep("waiting");

      const pollIntervalMs = parsePollIntervalMs(pickerSession.pollingConfig?.pollInterval);
      const ready = await pollUntilReady(accessToken, pickerSession.id, pickerSession.expireTime, pollIntervalMs);
      if (cancelledRef.current || !ready) return;

      const items = await listSessionMediaItems(accessToken, pickerSession.id);
      await runImport(accessToken, items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStep("category");
    }
  };

  return (
    <Modal title="Import from Google Photos" onClose={handleCancel}>
      <div className="space-y-4">
        {step === "category" && (
          <>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Choose which category imported photos should be added to, then sign in to Google Photos to pick them.
            </p>
            <SelectField
              label="Category"
              value={category}
              options={CATEGORIES}
              onChange={(v) => setCategory(v as ImageCategory)}
            />
            {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
            <button
              type="button"
              onClick={handleConnect}
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors cursor-pointer"
            >
              Continue with Google Photos
            </button>
          </>
        )}

        {step === "connecting" && (
          <p className="text-sm text-slate-500 dark:text-slate-400">Connecting to Google…</p>
        )}

        {step === "waiting" && (
          <>
            {pickerUri && (
              <a
                href={pickerUri}
                target="_blank"
                rel="noopener noreferrer"
                className="block w-full text-center bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors"
              >
                Open Google Photos to choose photos ↗
              </a>
            )}
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Choose photos in the tab that opened, then come back here — the import starts automatically once
              you&apos;re done selecting.
            </p>
            <button
              type="button"
              onClick={handleCancel}
              className="w-full bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 font-semibold py-2.5 rounded-lg text-sm cursor-pointer"
            >
              Cancel
            </button>
          </>
        )}

        {step === "importing" && (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Importing photo {Math.min(progress.done + 1, progress.total)} of {progress.total}…
          </p>
        )}

        {step === "summary" && result && (
          <>
            <p className="text-sm text-slate-700 dark:text-slate-300">
              Imported {result.imported} photo{result.imported === 1 ? "" : "s"}.
              {result.skipped > 0 &&
                ` Skipped ${result.skipped} item${result.skipped === 1 ? "" : "s"} (videos or unsupported formats).`}
            </p>
            {result.failed.length > 0 && (
              <ul className="text-xs text-red-600 dark:text-red-400 list-disc pl-4 space-y-0.5">
                {result.failed.map((f) => (
                  <li key={f.filename}>
                    {f.filename}: {f.reason}
                  </li>
                ))}
              </ul>
            )}
            <button
              type="button"
              onClick={onClose}
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors cursor-pointer"
            >
              Done
            </button>
          </>
        )}
      </div>
    </Modal>
  );
}
