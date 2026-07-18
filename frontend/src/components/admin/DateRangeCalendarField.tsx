"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { DayPicker, type DateRange } from "react-day-picker";
import { addMonths, format, isAfter, isBefore, isLastDayOfMonth, isWithinInterval, parse, startOfMonth } from "date-fns";
import "react-day-picker/style.css";

const ISO_FORMAT = "yyyy-MM-dd";

function parseISODate(value: string): Date | undefined {
  if (!value) return undefined;
  const parsed = parse(value, ISO_FORMAT, new Date());
  return Number.isNaN(parsed.getTime()) ? undefined : parsed;
}

/**
 * Picks which month a fresh range picker should open on, based on where the
 * previous row in the list left off: the month right after it when that row
 * ran through the end of its month, otherwise the same month.
 */
export function defaultMonthAfter(previousEndDate: string | undefined): Date | undefined {
  const end = previousEndDate ? parseISODate(previousEndDate) : undefined;
  if (!end) return undefined;
  return isLastDayOfMonth(end) ? addMonths(startOfMonth(end), 1) : startOfMonth(end);
}

export function DateRangeCalendarField({
  label,
  beginDate,
  endDate,
  onChange,
  blockedRanges,
  defaultMonth,
  minDate,
  maxDate,
  autoOpen,
}: {
  label: string;
  beginDate: string;
  endDate: string;
  onChange: (beginDate: string, endDate: string) => void;
  blockedRanges: { begin_date: string; end_date: string }[];
  defaultMonth?: Date;
  /** Days before this (ISO yyyy-MM-dd) are disabled, e.g. the enclosing period's begin date. */
  minDate?: string;
  /** Days after this (ISO yyyy-MM-dd) are disabled, e.g. the enclosing period's end date. */
  maxDate?: string;
  /** Opens the calendar as soon as this field mounts, e.g. for a row just added to a list. */
  autoOpen?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<DateRange | undefined>(undefined);
  // Document-relative (not viewport-relative) coordinates, so the popover is
  // plain in-flow content: if it's taller than the visible viewport, the
  // page itself grows a scrollbar instead of the overflow just being clipped.
  const [anchor, setAnchor] = useState<{ top: number; left: number } | null>(null);
  const fieldRef = useRef<HTMLDivElement>(null);
  const calendarRef = useRef<HTMLDivElement>(null);

  const commitPending = (value: DateRange | undefined) => {
    if (value?.from) onChange(format(value.from, ISO_FORMAT), value.to ? format(value.to, ISO_FORMAT) : "");
  };

  const openCalendar = () => {
    setPending({ from: parseISODate(beginDate), to: parseISODate(endDate) });
    setOpen(true);
  };

  const closeCalendar = () => {
    commitPending(pending);
    setOpen(false);
  };

  useEffect(() => {
    if (autoOpen) openCalendar();
    // Mount-only: fires once for a freshly added row, and must not re-fire
    // (or close) as `autoOpen` later flips back to false on the same instance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!open) return;
    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (fieldRef.current?.contains(target) || calendarRef.current?.contains(target)) return;
      closeCalendar();
    };
    // Capture phase so this resolves before Modal's own Escape handler closes
    // the whole dialog out from under an in-progress selection.
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      closeCalendar();
    };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown, true);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, pending]);

  // Portaled to <body> (escaping the modal's own scroll box and the date
  // ranges list's capped-height scroll box) and anchored with page-relative
  // coordinates, so a calendar that doesn't fit the viewport extends the
  // page's scrollable height rather than being clipped by either ancestor.
  useLayoutEffect(() => {
    if (!open) return;
    const updateAnchor = () => {
      if (!fieldRef.current) return;
      const rect = fieldRef.current.getBoundingClientRect();
      setAnchor({ top: rect.bottom + window.scrollY + 6, left: rect.left + window.scrollX });
    };
    updateAnchor();
    // Re-anchor when a nested container (the modal's own scroll box, or the
    // date ranges list's capped-height scroll box) scrolls, since that moves
    // the field on screen. Skip page-level scroll (event target === document)
    // so the popover stays put in page coordinates — that's what lets
    // scrolling the page bring an overflowing calendar into view instead of
    // having the popover chase the viewport and cancel the scroll out.
    const onScroll = (e: Event) => {
      if (e.target === document) return;
      updateAnchor();
    };
    window.addEventListener("resize", updateAnchor);
    document.addEventListener("scroll", onScroll, true);
    return () => {
      window.removeEventListener("resize", updateAnchor);
      document.removeEventListener("scroll", onScroll, true);
    };
  }, [open]);

  const blockedMatchers = blockedRanges
    .map((r) => ({ from: parseISODate(r.begin_date), to: parseISODate(r.end_date) }))
    .filter((r): r is { from: Date; to: Date } => !!r.from && !!r.to);

  const minDateParsed = parseISODate(minDate ?? "");
  const maxDateParsed = parseISODate(maxDate ?? "");
  const outsidePeriodMatchers = [
    ...(minDateParsed ? [{ before: minDateParsed }] : []),
    ...(maxDateParsed ? [{ after: maxDateParsed }] : []),
  ];
  const disabledMatchers = [...blockedMatchers, ...outsidePeriodMatchers];

  const isBlocked = (date: Date) =>
    blockedMatchers.some((r) => isWithinInterval(date, { start: r.from, end: r.to })) ||
    (!!minDateParsed && isBefore(date, minDateParsed)) ||
    (!!maxDateParsed && isAfter(date, maxDateParsed));

  const handleSelect = (selected: DateRange | undefined) => {
    // Belt-and-suspenders: DayPicker already refuses to select disabled days,
    // but never let a click that touches a blocked day mutate the pending
    // selection or close the popover.
    if ((selected?.from && isBlocked(selected.from)) || (selected?.to && isBlocked(selected.to))) return;
    setPending(selected);
    if (selected?.from && selected?.to) {
      onChange(format(selected.from, ISO_FORMAT), format(selected.to, ISO_FORMAT));
      setOpen(false);
    }
  };

  const displayText = beginDate && endDate ? `${beginDate} – ${endDate}` : beginDate || "Select dates";

  return (
    <div ref={fieldRef} className="relative">
      <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">{label}</label>
      <button
        type="button"
        onClick={() => (open ? closeCalendar() : openCalendar())}
        className={`w-full text-left px-3 py-2 rounded-lg border text-sm transition-colors focus:outline-none focus:ring-1 focus:ring-indigo-400 cursor-pointer ${
          open ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40" : "border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 hover:border-slate-400"
        } ${beginDate ? "text-slate-800 dark:text-slate-100" : "text-slate-400 dark:text-slate-500"}`}
      >
        {displayText}
      </button>

      {open &&
        anchor &&
        createPortal(
          <div
            ref={calendarRef}
            className="absolute z-[120] bg-white dark:bg-slate-800 rounded-xl shadow-2xl border border-slate-200 dark:border-slate-700 p-3"
            style={{ top: anchor.top, left: anchor.left }}
          >
            <DayPicker
              mode="range"
              selected={pending}
              defaultMonth={defaultMonth ?? pending?.from ?? new Date()}
              onSelect={handleSelect}
              onDayClick={(date, modifiers) => {
                if (modifiers.disabled) return;
                if (pending?.from && pending?.to) setPending({ from: date, to: undefined });
              }}
              disabled={disabledMatchers}
              numberOfMonths={1}
              min={1}
            />
          </div>,
          document.body
        )}
    </div>
  );
}
