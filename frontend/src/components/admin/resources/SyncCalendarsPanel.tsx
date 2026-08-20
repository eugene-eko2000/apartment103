"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  calendarExportUrl,
  createExternalCalendar,
  deleteExternalCalendar,
  listExternalCalendars,
  syncAllExternalCalendars,
  syncExternalCalendar,
  updateExternalCalendar,
  type CalendarSyncResult,
  type ExternalCalendar,
  type ExternalCalendarInput,
} from "@/lib/api";
import { useAdminAuth } from "@/lib/admin-auth";
import { DataTable, type Column } from "../DataTable";
import { Modal } from "../Modal";
import { SubmitButton, TextField } from "../FormFields";

const emptyForm: ExternalCalendarInput = { name: "", url: "" };

function CopyableUrl({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be blocked (non-HTTPS origin, permissions);
      // the URL is on screen and selectable either way.
      window.prompt("Copy this URL", url);
    }
  };

  return (
    <span className="inline-flex items-center gap-2">
      <code className="text-xs text-slate-500 dark:text-slate-400 max-w-[13rem] truncate" title={url}>
        {url}
      </code>
      <button
        type="button"
        onClick={copy}
        className="text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 text-xs font-medium cursor-pointer"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </span>
  );
}

function SyncStatusCell({ calendar }: { calendar: ExternalCalendar }) {
  if (!calendar.last_synced_at) {
    return <span className="text-slate-400 dark:text-slate-500">Never synced</span>;
  }
  const when = new Date(calendar.last_synced_at).toLocaleString([], {
    dateStyle: "short",
    timeStyle: "short",
  });
  if (calendar.last_sync_status === "error") {
    return (
      <span className="text-red-600 dark:text-red-400" title={calendar.last_sync_error ?? undefined}>
        Failed · {when}
      </span>
    );
  }
  return (
    <span className="text-slate-500 dark:text-slate-400">
      {when}
      {calendar.last_sync_block_count !== null && (
        <span className="text-slate-400 dark:text-slate-500">
          {" "}
          · {calendar.last_sync_block_count} blocked
        </span>
      )}
    </span>
  );
}

export default function SyncCalendarsPanel() {
  const { session, logout } = useAdminAuth();
  const token = session!.token;

  const [calendars, setCalendars] = useState<ExternalCalendar[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [editing, setEditing] = useState<ExternalCalendar | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<ExternalCalendarInput>(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const [syncing, setSyncing] = useState<string | null>(null);
  const [syncResults, setSyncResults] = useState<CalendarSyncResult[] | null>(null);

  const load = () => {
    listExternalCalendars(token)
      .then((data) => {
        setCalendars(data);
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

  const openEdit = (calendar: ExternalCalendar) => {
    setEditing(calendar);
    setForm({ name: calendar.name, url: calendar.url });
    setFormError(null);
    setShowModal(true);
  };

  const handleDelete = async (calendar: ExternalCalendar) => {
    if (
      !window.confirm(
        `Delete the "${calendar.name}" calendar? Dates imported from it stay blocked until you remove them under Closures, and its export URL stops working.`,
      )
    )
      return;
    try {
      await deleteExternalCalendar(calendar._id, token);
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      window.alert(err instanceof ApiError ? err.message : String(err));
    }
  };

  const handleBulkDelete = async (selected: ExternalCalendar[]) => {
    if (!window.confirm(`Delete ${selected.length} calendar${selected.length === 1 ? "" : "s"}?`)) return;
    try {
      await Promise.all(selected.map((calendar) => deleteExternalCalendar(calendar._id, token)));
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
        await updateExternalCalendar(editing._id, token, form);
      } else {
        await createExternalCalendar(token, form);
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

  const runSync = async (calendar: ExternalCalendar | null) => {
    setSyncing(calendar?._id ?? "all");
    setSyncResults(null);
    try {
      const results = calendar
        ? [await syncExternalCalendar(calendar._id, token)]
        : await syncAllExternalCalendars(token);
      setSyncResults(results);
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return logout();
      window.alert(err instanceof ApiError ? err.message : String(err));
    } finally {
      setSyncing(null);
    }
  };

  const columns: Column<ExternalCalendar>[] = [
    { key: "name", label: "Name", render: (c) => <span className="font-medium">{c.name}</span> },
    {
      key: "url",
      label: "Import URL (theirs)",
      render: (c) => (
        <code className="text-xs text-slate-500 dark:text-slate-400 max-w-[11rem] truncate inline-block align-bottom" title={c.url}>
          {c.url}
        </code>
      ),
    },
    {
      key: "export_url",
      label: "Export URL (ours)",
      render: (c) => <CopyableUrl url={calendarExportUrl(c.export_token)} />,
    },
    { key: "last_sync", label: "Last sync", render: (c) => <SyncStatusCell calendar={c} /> },
    {
      key: "sync",
      label: "",
      render: (c) => (
        <button
          type="button"
          onClick={() => runSync(c)}
          disabled={syncing !== null}
          className="text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 disabled:opacity-50 text-xs font-medium cursor-pointer"
        >
          {syncing === c._id ? "Syncing…" : "Sync now"}
        </button>
      ),
    },
  ];

  return (
    <div>
      <div className="mb-6 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4 text-sm text-slate-600 dark:text-slate-300">
        <h2 className="font-semibold text-slate-800 dark:text-slate-100 mb-2">How calendar sync works</h2>
        <p className="mb-2">
          Availability is exchanged with Airbnb, Booking.com and any other calendar app as iCal
          (.ics) feeds — the same &ldquo;sync calendars&rdquo; feature those platforms offer hosts.
          For each platform, set it up in both directions:
        </p>
        <ul className="list-disc pl-5 space-y-1">
          <li>
            <strong>Them &rarr; us:</strong> paste that platform&rsquo;s calendar <em>export</em>{" "}
            link below as the import URL. Every {" "}
            <span className="whitespace-nowrap">30 minutes</span> their booked dates are pulled in
            and appear under Closures, which blocks them on this site.
          </li>
          <li>
            <strong>Us &rarr; them:</strong>{" "}copy the export URL below and paste it into that
            platform&rsquo;s &ldquo;import calendar&rdquo; setting, once. It publishes every booking
            taken here (plus closures from the other platforms) as opaque &ldquo;Reserved&rdquo;
            dates — no guest names or prices.
          </li>
        </ul>
        <p className="mt-2 text-slate-500 dark:text-slate-400">
          Both platforms refresh imported calendars on their own schedule, so a reservation can take
          a few hours to show up on the other side. Use &ldquo;Sync now&rdquo; right after you see a
          new reservation to pull it in immediately.
        </p>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <button
          type="button"
          onClick={() => runSync(null)}
          disabled={syncing !== null || calendars.length === 0}
          className="bg-slate-800 dark:bg-slate-700 hover:bg-slate-900 dark:hover:bg-slate-600 disabled:opacity-50 text-white text-sm font-semibold px-4 py-2 rounded-lg cursor-pointer transition-colors"
        >
          {syncing === "all" ? "Syncing…" : "Sync all now"}
        </button>
        {syncResults && (
          <div className="text-sm space-y-0.5">
            {syncResults.map((result) => (
              <p
                key={result.calendar_id}
                className={
                  result.status === "ok"
                    ? "text-slate-600 dark:text-slate-300"
                    : "text-red-600 dark:text-red-400"
                }
              >
                {result.status === "ok"
                  ? `${result.calendar_name}: ${result.created} added, ${result.updated} unchanged, ${result.deleted} removed`
                  : `${result.calendar_name}: ${result.error}`}
              </p>
            ))}
          </div>
        )}
      </div>

      <DataTable
        columns={columns}
        rows={calendars}
        rowKey={(c) => c._id}
        onEdit={openEdit}
        onDelete={handleDelete}
        onBulkDelete={handleBulkDelete}
        onCreate={openCreate}
        createLabel="New calendar"
        loading={loading}
        error={listError}
        emptyLabel="No external calendars yet."
      />

      {showModal && (
        <Modal
          title={editing ? "Edit calendar" : "New calendar"}
          onClose={() => setShowModal(false)}
          footer={
            <SubmitButton
              form="external-calendar-form"
              pending={pending}
              label={editing ? "Save changes" : "Create calendar"}
            />
          }
        >
          <form id="external-calendar-form" onSubmit={handleSubmit} className="space-y-4">
            <TextField
              label="Name"
              value={form.name}
              placeholder="e.g. Airbnb, Booking.com"
              onChange={(v) => setForm((p) => ({ ...p, name: v }))}
            />
            <TextField
              label="Import URL (.ics export link from that platform)"
              value={form.url}
              placeholder="https://www.airbnb.com/calendar/ical/12345.ics?s=…"
              onChange={(v) => setForm((p) => ({ ...p, url: v }))}
            />
            <p className="text-xs text-slate-500 dark:text-slate-400">
              On Airbnb: Calendar &rarr; Availability &rarr; Connect to another website &rarr; Export
              calendar. On Booking.com: Rates &amp; Availability &rarr; Sync calendars &rarr; Export
              calendar. Dates imported from this feed are labelled with the name above.
            </p>
            {editing && (
              <div>
                <p className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">
                  Export URL — paste this into that platform&rsquo;s &ldquo;import calendar&rdquo;
                  setting
                </p>
                <CopyableUrl url={calendarExportUrl(editing.export_token)} />
              </div>
            )}
            {formError && <p className="text-sm text-red-600 dark:text-red-400">{formError}</p>}
          </form>
        </Modal>
      )}
    </div>
  );
}
