"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { COUNTRIES, countryFlag } from "@/lib/countries";

const display = (name: string) => (name ? `${countryFlag(name)} ${name}` : "");

const TONE_CLASSES = {
  booking: {
    label: "text-gray-500 dark:text-gray-400",
    field:
      "rounded-xl border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 focus:ring-teal-300 focus:border-teal-400",
    panel: "border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800",
    item: "hover:bg-gray-50 dark:hover:bg-gray-700",
    highlighted: "bg-gray-50 dark:bg-gray-700",
    empty: "text-gray-400 dark:text-gray-500",
  },
  admin: {
    label: "text-slate-500 dark:text-slate-400",
    field:
      "rounded-lg border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 focus:ring-indigo-400 focus:border-indigo-500",
    panel: "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-700",
    item: "hover:bg-slate-100 dark:hover:bg-slate-600",
    highlighted: "bg-slate-100 dark:bg-slate-600",
    empty: "text-slate-400 dark:text-slate-500",
  },
} as const;

// A searchable country picker: a text input filters the (hardcoded) country
// list live as the guest types — e.g. "Swe" narrows straight to Sweden —
// which a plain <select>'s native typeahead can't do once each option's
// text starts with a flag emoji instead of a letter.
export function CountrySelect({
  label,
  value,
  onChange,
  noneLabel,
  required = true,
  tone = "booking",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  noneLabel: string;
  required?: boolean;
  tone?: keyof typeof TONE_CLASSES;
}) {
  const id = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  // Only holds the in-progress search text while the listbox is open; while
  // closed the field just shows display(value) directly, computed on every
  // render, so it can never drift out of sync with value (e.g. a guest
  // profile finishing its fetch after this mounts).
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const classes = TONE_CLASSES[tone];
  const inputValue = open ? query : display(value);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || q === display(value).toLowerCase()) return COUNTRIES;
    return COUNTRIES.filter((c) => c.name.toLowerCase().includes(q));
  }, [query, value]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const select = (name: string) => {
    onChange(name);
    setOpen(false);
  };

  return (
    <div ref={rootRef} className="relative">
      <label htmlFor={id} className={`block text-xs font-medium mb-1 ${classes.label}`}>
        {label}
      </label>
      <input
        id={id}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={`${id}-listbox`}
        aria-autocomplete="list"
        autoComplete="off"
        required={required}
        placeholder={noneLabel}
        value={inputValue}
        onFocus={(e) => {
          setQuery(display(value));
          setOpen(true);
          setHighlighted(0);
          e.target.select();
        }}
        onChange={(e) => {
          const next = e.target.value;
          setQuery(next);
          setOpen(true);
          setHighlighted(0);
          // Commit as soon as the typed text exactly names a real country,
          // even without an explicit Enter/click — otherwise typing the
          // full correct name and clicking straight into the next field
          // would blur-revert it away as if nothing had been chosen.
          const exact = COUNTRIES.find((c) => c.name.toLowerCase() === next.trim().toLowerCase());
          if (exact) onChange(exact.name);
        }}
        onBlur={() => {
          // A click on an option is handled via onMouseDown (which
          // preventDefault()s the blur), so a blur reaching here means focus
          // left without a selection — discard whatever was typed; once
          // closed, the field shows display(value) directly.
          setOpen(false);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setOpen(true);
            setHighlighted((i) => Math.min(i + 1, filtered.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setHighlighted((i) => Math.max(i - 1, 0));
          } else if (e.key === "Enter" && open && filtered[highlighted]) {
            e.preventDefault();
            select(filtered[highlighted].name);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
        className={`w-full px-3 py-2 text-sm border focus:outline-none focus:ring-1 cursor-text ${classes.field}`}
      />
      {open && (
        <ul
          id={`${id}-listbox`}
          role="listbox"
          className={`absolute z-50 mt-1 max-h-56 w-full overflow-auto rounded-lg border shadow-lg py-1 text-sm ${classes.panel}`}
        >
          {filtered.length === 0 ? (
            <li className={`px-3 py-2 ${classes.empty}`}>No matches</li>
          ) : (
            filtered.map((c, i) => (
              <li
                key={c.name}
                role="option"
                aria-selected={c.name === value}
                onMouseDown={(e) => {
                  e.preventDefault();
                  select(c.name);
                }}
                onMouseEnter={() => setHighlighted(i)}
                className={`px-3 py-1.5 cursor-pointer ${i === highlighted ? classes.highlighted : classes.item}`}
              >
                {c.flag} {c.name}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
