// Placeholders an automated guest message may use, and the editor logic
// around them. Mirrors PLACEHOLDERS in the backend's
// app/models/message_template.py, which substitutes the real values per
// booking and rejects any name not listed there.

import type { MessageAnchor, MessageDirection } from "./api";

export interface Placeholder {
  name: string;
  label: string;
}

export const PLACEHOLDERS: Placeholder[] = [
  { name: "guest_first_name", label: "Guest's first name" },
  { name: "guest_last_name", label: "Guest's last name" },
  { name: "checkin_date", label: "Check-in date" },
  { name: "checkout_date", label: "Check-out date" },
  { name: "stay_days", label: "Number of nights" },
  { name: "adults_number", label: "Number of adults" },
  { name: "children_older_6yo_number", label: "Children aged 6 or older" },
  { name: "children_below_6yo_number", label: "Children younger than 6" },
];

const PLACEHOLDER_NAMES = new Set(PLACEHOLDERS.map((p) => p.name));

// Same stand-in values the backend's test send uses (SAMPLE_VALUES in
// app/services/guest_messages.py), so the preview matches that email.
export const SAMPLE_VALUES: Record<string, string> = {
  guest_first_name: "Anna",
  guest_last_name: "Muster",
  checkin_date: "12.11.2026",
  checkout_date: "16.11.2026",
  stay_days: "4",
  adults_number: "2",
  children_older_6yo_number: "1",
  children_below_6yo_number: "1",
};

export const placeholderToken = (name: string) => `{{${name}}}`;

// `{{ name }}`, tolerating spaces inside the braces — same as the backend.
const PLACEHOLDER_PATTERN = /\{\{\s*([^{}]*?)\s*\}\}/g;

export function substitutePlaceholders(text: string, values: Record<string, string>): string {
  return text.replace(PLACEHOLDER_PATTERN, (match, name: string) =>
    PLACEHOLDER_NAMES.has(name) ? (values[name] ?? "") : match
  );
}

export function unknownPlaceholders(text: string): string[] {
  const unknown = new Set<string>();
  for (const [, name] of text.matchAll(PLACEHOLDER_PATTERN)) {
    if (!PLACEHOLDER_NAMES.has(name)) unknown.add(name);
  }
  return [...unknown].sort();
}

export interface PlaceholderTrigger {
  /** Index of the opening "{{". */
  start: number;
  /** What has been typed after it so far. */
  query: string;
}

/**
 * The unfinished `{{…` the caret sits right after, if any — what opens the
 * autocomplete. Only placeholder-name characters may follow the braces, so
 * typing a space, a closing brace or anything else dismisses it.
 */
export function findPlaceholderTrigger(text: string, caret: number): PlaceholderTrigger | null {
  const match = /\{\{\s*([a-z0-9_]*)$/i.exec(text.slice(0, caret));
  return match ? { start: match.index, query: match[1] } : null;
}

/** Placeholders matching `query`: prefix matches first, then substring matches. */
export function matchPlaceholders(query: string): Placeholder[] {
  const q = query.toLowerCase();
  const prefix = PLACEHOLDERS.filter((p) => p.name.startsWith(q));
  const inner = PLACEHOLDERS.filter((p) => !p.name.startsWith(q) && p.name.includes(q));
  return [...prefix, ...inner];
}

/**
 * The span an accepted completion replaces: from the "{{" to the caret, plus
 * a "}}" already sitting right after the caret, so completing inside
 * `{{gu|}}` doesn't leave `{{guest_first_name}}}}` behind.
 */
export function completionRange(text: string, trigger: PlaceholderTrigger, caret: number): [number, number] {
  return [trigger.start, text.startsWith("}}", caret) ? caret + 2 : caret];
}

/** Plain-text splice, for when the browser can't insert through execCommand. */
export function spliceText(text: string, start: number, end: number, insert: string): string {
  return text.slice(0, start) + insert + text.slice(end);
}

const ANCHOR_LABELS: Record<MessageAnchor, string> = {
  booking_date: "booking",
  checkin: "check-in",
  checkout: "check-out",
};

/** "1 day after booking", "2 days before check-in", "On the check-out day". */
export function describeSchedule(schedule: {
  anchor: MessageAnchor;
  direction: MessageDirection;
  offset_days: number;
}): string {
  const anchor = ANCHOR_LABELS[schedule.anchor];
  if (!Number.isFinite(schedule.offset_days)) return "—";
  if (schedule.offset_days === 0) return schedule.anchor === "booking_date" ? "On the booking day" : `On the ${anchor} day`;
  const days = `${schedule.offset_days} day${schedule.offset_days === 1 ? "" : "s"}`;
  return `${days} ${schedule.direction} ${anchor}`;
}
