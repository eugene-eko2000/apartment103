"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  createMessageTemplate,
  deleteMessageTemplate,
  getMessageTemplateStats,
  listMessageDeliveries,
  listMessageTemplates,
  sendTestMessage,
  updateMessageTemplate,
  type Language,
  type MessageAnchor,
  type MessageDelivery,
  type MessageDirection,
  type MessageTemplate,
  type MessageTemplateInput,
  type MessageTemplateStats,
  type MessageTemplateVersion,
} from "@/lib/api";
import { useAdminAuth } from "@/lib/admin-auth";
import { describeSchedule, unknownPlaceholders } from "@/lib/message-placeholders";
import { DataTable, type Column } from "../DataTable";
import { Modal } from "../Modal";
import { NumberField, SelectField, SubmitButton, TextField } from "../FormFields";
import MessageVersionEditor from "../MessageVersionEditor";

const LANGUAGES: { value: Language; label: string }[] = [
  { value: "en", label: "English" },
  { value: "de", label: "Deutsch" },
  { value: "fr", label: "Français" },
  { value: "it", label: "Italiano" },
];
const languageLabel = (language: Language) => LANGUAGES.find((l) => l.value === language)?.label ?? language;

const ANCHORS: { value: MessageAnchor; label: string }[] = [
  { value: "booking_date", label: "booking date" },
  { value: "checkin", label: "check-in date" },
  { value: "checkout", label: "check-out date" },
];

const emptyVersion = (language: Language): MessageTemplateVersion => ({ language, subject: "", body_markdown: "" });

// English first: it is the version a guest without one in their own
// language receives.
const emptyForm = (): MessageTemplateInput => ({
  name: "",
  anchor: "checkin",
  direction: "before",
  offset_days: 1,
  versions: [emptyVersion("en")],
  active: true,
});

/** First problem with the form, checked before it is sent so the admin gets a readable message rather than a 422. */
function validate(form: MessageTemplateInput): string | null {
  if (!Number.isInteger(form.offset_days) || form.offset_days < 0) return "Days must be a whole number, 0 or more.";
  for (const version of form.versions) {
    const name = languageLabel(version.language);
    if (!version.subject.trim()) return `The ${name} version needs a subject.`;
    if (!version.body_markdown.trim()) return `The ${name} version needs a message text.`;
    const unknown = unknownPlaceholders(version.subject + "\n" + version.body_markdown);
    if (unknown.length > 0)
      return `Unknown placeholder${unknown.length > 1 ? "s" : ""} in the ${name} version: ${unknown
        .map((n) => `{{${n}}}`)
        .join(", ")}`;
  }
  return null;
}

const STATUS_STYLES: Record<string, string> = {
  sent: "text-emerald-700 dark:text-emerald-400",
  failed: "text-red-600 dark:text-red-400",
  skipped: "text-slate-500 dark:text-slate-400",
  pending: "text-amber-600 dark:text-amber-400",
};

export default function GuestMessagesPanel() {
  const { session, logout } = useAdminAuth();
  const token = session!.token;

  const [templates, setTemplates] = useState<MessageTemplate[]>([]);
  const [stats, setStats] = useState<Record<string, MessageTemplateStats>>({});
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [editing, setEditing] = useState<MessageTemplate | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<MessageTemplateInput>(emptyForm);
  const [activeLanguage, setActiveLanguage] = useState<Language>("en");
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [testStatus, setTestStatus] = useState<string | null>(null);
  const [deliveries, setDeliveries] = useState<MessageDelivery[] | null>(null);

  const handleError = (err: unknown, show: (message: string) => void) => {
    if (err instanceof ApiError && err.status === 401) return logout();
    show(err instanceof ApiError ? err.message : String(err));
  };

  const load = () => {
    Promise.all([listMessageTemplates(token), getMessageTemplateStats(token)])
      .then(([data, statRows]) => {
        setTemplates(data);
        setStats(Object.fromEntries(statRows.map((row) => [row.template_id, row])));
        setListError(null);
      })
      .catch((err) => handleError(err, setListError))
      .finally(() => setLoading(false));
  };

  useEffect(load, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  const openModal = (template: MessageTemplate | null) => {
    setEditing(template);
    setForm(
      template
        ? {
            name: template.name,
            anchor: template.anchor,
            direction: template.direction,
            offset_days: template.offset_days,
            versions: template.versions,
            active: template.active,
          }
        : emptyForm()
    );
    setActiveLanguage(template?.versions[0]?.language ?? "en");
    setFormError(null);
    setTestStatus(null);
    setDeliveries(null);
    setShowModal(true);
    if (template) {
      listMessageDeliveries(template._id, token)
        .then(setDeliveries)
        .catch(() => setDeliveries([]));
    }
  };

  const handleDelete = async (template: MessageTemplate) => {
    if (!window.confirm(`Delete the message "${template.name}"?`)) return;
    try {
      await deleteMessageTemplate(template._id, token);
      load();
    } catch (err) {
      handleError(err, (message) => window.alert(message));
    }
  };

  const handleBulkDelete = async (selected: MessageTemplate[]) => {
    if (!window.confirm(`Delete ${selected.length} message${selected.length === 1 ? "" : "s"}?`)) return;
    try {
      await Promise.all(selected.map((t) => deleteMessageTemplate(t._id, token)));
      load();
    } catch (err) {
      handleError(err, (message) => window.alert(message));
    }
  };

  const handleSubmit = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    const problem = validate(form);
    if (problem) {
      setFormError(problem);
      return;
    }
    setPending(true);
    setFormError(null);
    try {
      if (editing) await updateMessageTemplate(editing._id, token, form);
      else await createMessageTemplate(token, form);
      setShowModal(false);
      load();
    } catch (err) {
      handleError(err, setFormError);
    } finally {
      setPending(false);
    }
  };

  const handleTestSend = async () => {
    if (!editing) return;
    setTestStatus("Sending…");
    try {
      const result = await sendTestMessage(editing._id, token, activeLanguage);
      setTestStatus(`Sent "${result.subject}" to ${result.to}.`);
    } catch (err) {
      handleError(err, setTestStatus);
    }
  };

  const updateVersion = (updated: MessageTemplateVersion) =>
    setForm((p) => ({ ...p, versions: p.versions.map((v) => (v.language === updated.language ? updated : v)) }));

  const addLanguage = (language: Language) => {
    setForm((p) => ({ ...p, versions: [...p.versions, emptyVersion(language)] }));
    setActiveLanguage(language);
  };

  const removeLanguage = (language: Language) => {
    if (!window.confirm(`Remove the ${languageLabel(language)} version?`)) return;
    const remaining = form.versions.filter((v) => v.language !== language);
    setForm((p) => ({ ...p, versions: remaining }));
    setActiveLanguage(remaining[0].language);
  };

  const setAnchor = (anchor: MessageAnchor) =>
    // Nothing can be sent before the guest has booked.
    setForm((p) => ({ ...p, anchor, direction: anchor === "booking_date" ? "after" : p.direction }));

  const columns: Column<MessageTemplate>[] = [
    { key: "name", label: "Name", render: (t) => t.name },
    { key: "schedule", label: "Schedule", render: (t) => describeSchedule(t) },
    {
      key: "languages",
      label: "Languages",
      render: (t) => (
        <span className="flex gap-1">
          {t.versions.map((v) => (
            <span
              key={v.language}
              className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-xs font-semibold uppercase text-slate-600 dark:text-slate-300"
            >
              {v.language}
            </span>
          ))}
        </span>
      ),
    },
    {
      key: "active",
      label: "Status",
      render: (t) =>
        t.active ? (
          <span className="text-emerald-700 dark:text-emerald-400">Active</span>
        ) : (
          <span className="text-slate-400">Paused</span>
        ),
    },
    {
      key: "deliveries",
      label: "Delivered",
      render: (t) => {
        const row = stats[t._id];
        if (!row) return "0";
        return row.failed > 0 ? `${row.sent} (${row.failed} failed)` : String(row.sent);
      },
    },
  ];

  const activeVersion = form.versions.find((v) => v.language === activeLanguage) ?? form.versions[0];
  const missingLanguages = LANGUAGES.filter((l) => !form.versions.some((v) => v.language === l.value));

  return (
    <div>
      <p className="mb-4 text-sm text-slate-500 dark:text-slate-400">
        Messages are emailed automatically every day at 12:00 UTC to guests with a confirmed booking, together with an
        SMS pointing them to their inbox. Each guest gets the version in their language, or English.
      </p>
      <DataTable
        columns={columns}
        rows={templates}
        rowKey={(t) => t._id}
        onEdit={(t) => openModal(t)}
        onDelete={handleDelete}
        onBulkDelete={handleBulkDelete}
        onCreate={() => openModal(null)}
        createLabel="New message"
        loading={loading}
        error={listError}
        emptyLabel="No guest messages yet."
      />

      {showModal && (
        <Modal
          title={editing ? "Edit message" : "New message"}
          onClose={() => setShowModal(false)}
          maxWidth="max-w-4xl"
          footer={
            <SubmitButton form="message-form" pending={pending} label={editing ? "Save changes" : "Create message"} />
          }
        >
          <form id="message-form" onSubmit={handleSubmit} className="space-y-5">
            <TextField
              label="Name (only shown here)"
              value={form.name}
              placeholder="e.g. Arrival instructions"
              onChange={(v) => setForm((p) => ({ ...p, name: v }))}
            />

            <fieldset>
              <legend className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Send</legend>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <NumberField
                  label="Days"
                  value={form.offset_days}
                  min={0}
                  max={365}
                  step={1}
                  onChange={(v) => setForm((p) => ({ ...p, offset_days: v }))}
                />
                <SelectField<MessageDirection>
                  label="Before / after"
                  value={form.direction}
                  options={
                    form.anchor === "booking_date"
                      ? [{ value: "after", label: "after" }]
                      : [
                          { value: "before", label: "before" },
                          { value: "after", label: "after" },
                        ]
                  }
                  onChange={(v) => setForm((p) => ({ ...p, direction: v }))}
                />
                <SelectField<MessageAnchor> label="Date" value={form.anchor} options={ANCHORS} onChange={setAnchor} />
              </div>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300" data-testid="schedule-summary">
                {describeSchedule(form)}
              </p>
            </fieldset>

            <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200 cursor-pointer">
              <input
                type="checkbox"
                checked={form.active}
                onChange={(e) => setForm((p) => ({ ...p, active: e.target.checked }))}
                className="accent-indigo-600"
              />
              Active
            </label>

            <section>
              <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 dark:border-slate-700 mb-4">
                <div className="flex gap-1" role="tablist" aria-label="Language versions">
                  {form.versions.map((v) => (
                    <button
                      key={v.language}
                      type="button"
                      role="tab"
                      aria-selected={v.language === activeVersion.language}
                      onClick={() => setActiveLanguage(v.language)}
                      className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px cursor-pointer ${
                        v.language === activeVersion.language
                          ? "border-indigo-600 text-indigo-700 dark:text-indigo-400"
                          : "border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-100"
                      }`}
                    >
                      {languageLabel(v.language)}
                    </button>
                  ))}
                </div>
                {missingLanguages.length > 0 && (
                  <select
                    aria-label="Add language"
                    value=""
                    onChange={(e) => addLanguage(e.target.value as Language)}
                    className="ml-auto mb-1 px-2 py-1 rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-sm text-slate-700 dark:text-slate-200 cursor-pointer"
                  >
                    <option value="">+ Add language</option>
                    {missingLanguages.map((l) => (
                      <option key={l.value} value={l.value}>
                        {l.label}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <MessageVersionEditor key={activeVersion.language} version={activeVersion} onChange={updateVersion} />

              <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
                {form.versions.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeLanguage(activeVersion.language)}
                    className="text-red-600 dark:text-red-400 hover:underline cursor-pointer"
                  >
                    Remove {languageLabel(activeVersion.language)} version
                  </button>
                )}
                {editing && (
                  <button
                    type="button"
                    onClick={handleTestSend}
                    className="text-indigo-700 dark:text-indigo-400 hover:underline cursor-pointer"
                  >
                    Email me the saved {languageLabel(activeVersion.language)} version
                  </button>
                )}
                {testStatus && <span className="text-slate-500 dark:text-slate-400">{testStatus}</span>}
              </div>
            </section>

            {formError && <p className="text-sm text-red-600 dark:text-red-400">{formError}</p>}

            {editing && (
              <section>
                <h3 className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-2">Delivery history</h3>
                {deliveries === null ? (
                  <p className="text-sm text-slate-400">Loading…</p>
                ) : deliveries.length === 0 ? (
                  <p className="text-sm text-slate-400">Not sent to anyone yet.</p>
                ) : (
                  <div className="max-h-48 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-700">
                    <table className="w-full text-xs">
                      <thead className="bg-slate-50 dark:bg-slate-700/50 text-slate-500 dark:text-slate-400">
                        <tr>
                          <th className="text-left px-3 py-1.5 font-medium">Due</th>
                          <th className="text-left px-3 py-1.5 font-medium">Recipient</th>
                          <th className="text-left px-3 py-1.5 font-medium">Language</th>
                          <th className="text-left px-3 py-1.5 font-medium">Email</th>
                          <th className="text-left px-3 py-1.5 font-medium">SMS</th>
                        </tr>
                      </thead>
                      <tbody className="text-slate-700 dark:text-slate-200">
                        {deliveries.map((d) => (
                          <tr key={d._id} className="border-t border-slate-100 dark:border-slate-700">
                            <td className="px-3 py-1.5">{d.scheduled_for}</td>
                            <td className="px-3 py-1.5">{d.recipient_email ?? "—"}</td>
                            <td className="px-3 py-1.5 uppercase">{d.language ?? "—"}</td>
                            <td className={`px-3 py-1.5 ${STATUS_STYLES[d.email_status]}`} title={d.email_error ?? ""}>
                              {d.email_status}
                            </td>
                            <td className={`px-3 py-1.5 ${STATUS_STYLES[d.sms_status]}`} title={d.sms_error ?? ""}>
                              {d.sms_status}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            )}
          </form>
        </Modal>
      )}
    </div>
  );
}
