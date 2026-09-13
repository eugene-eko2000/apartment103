"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { COUNTRIES, countryFlag, localizedCountryName } from "@/lib/countries";
import { FieldChevron, TONE_CLASSES } from "@/components/field-chrome";
import type { Locale } from "@/lib/i18n-config";

const display = (name: string, locale: Locale) =>
  name ? `${countryFlag(name)} ${localizedCountryName(name, locale)}` : "";

// A searchable country picker: a text input filters the (hardcoded) country
// list live as the guest types — e.g. "Swe" narrows straight to Sweden —
// which a plain <select>'s native typeahead can't do once each option's
// text starts with a flag emoji instead of a letter.
export function CountrySelect({
  label,
  value,
  onChange,
  noneLabel,
  noMatchesLabel = "No matches",
  required = true,
  tone = "booking",
  locale = "en",
  valid = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  noneLabel: string;
  noMatchesLabel?: string;
  required?: boolean;
  tone?: keyof typeof TONE_CLASSES;
  locale?: Locale;
  valid?: boolean;
}) {
  const id = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const itemRefs = useRef<(HTMLLIElement | null)[]>([]);
  // Only holds the in-progress search text while the listbox is open; while
  // closed the field just shows display(value) directly, computed on every
  // render, so it can never drift out of sync with value (e.g. a guest
  // profile finishing its fetch after this mounts).
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const classes = TONE_CLASSES[tone];
  const inputValue = open ? query : display(value, locale);

  // Localized name, sorted for that locale's alphabet — recomputed only when
  // the locale changes, not on every keystroke.
  const localizedCountries = useMemo(
    () =>
      COUNTRIES.map((c) => ({ ...c, displayName: localizedCountryName(c.name, locale) })).sort((a, b) =>
        a.displayName.localeCompare(b.displayName, locale)
      ),
    [locale]
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || q === display(value, locale).toLowerCase()) return localizedCountries;
    return localizedCountries.filter((c) => c.displayName.toLowerCase().includes(q));
  }, [query, value, locale, localizedCountries]);

  // Scroll the highlighted option into view whenever the listbox opens (so
  // it lands on the currently selected country, not the top of the list) or
  // the highlight moves via keyboard.
  useEffect(() => {
    if (!open) return;
    itemRefs.current[highlighted]?.scrollIntoView({ block: "nearest" });
  }, [open, highlighted]);

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

  // Opening always lands the highlight (and, via the scroll effect above, the
  // viewport) on the already-selected country instead of the top of the list.
  const openList = () => {
    setQuery(display(value, locale));
    const selectedIndex = localizedCountries.findIndex((c) => c.name === value);
    setHighlighted(selectedIndex === -1 ? 0 : selectedIndex);
    setOpen(true);
  };

  // What the chevron does: the field itself only ever opens (focusing it
  // starts a search), so closing again is the chevron's job alone.
  const toggleList = () => {
    if (open) {
      setOpen(false);
      return;
    }
    openList();
    inputRef.current?.focus();
    inputRef.current?.select();
  };

  return (
    <div ref={rootRef} className="relative">
      <label htmlFor={id} className={`block text-xs font-medium mb-1 ${classes.label}`}>
        {label}
      </label>
      {/* Input and chevron share their own positioning context, so the chevron
          can stretch to the field's height (inset-y-0) rather than naming it —
          the label above stays outside this box. */}
      <div className="relative">
        <input
          ref={inputRef}
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
            openList();
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
            const exact = localizedCountries.find((c) => c.displayName.toLowerCase() === next.trim().toLowerCase());
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
          className={`w-full pl-3 pr-8 py-2 text-sm border focus:outline-none focus:ring-1 cursor-text ${
            valid ? classes.validField : classes.field
          }`}
        />
        <FieldChevron open={open} tone={tone} onToggle={toggleList} />
      </div>
      {open && (
        <ul
          id={`${id}-listbox`}
          role="listbox"
          className={`absolute z-50 mt-1 max-h-56 w-full overflow-auto rounded-lg border shadow-lg py-1 text-sm ${classes.panel}`}
        >
          {filtered.length === 0 ? (
            <li className={`px-3 py-2 ${classes.empty}`}>{noMatchesLabel}</li>
          ) : (
            filtered.map((c, i) => (
              <li
                key={c.name}
                ref={(el) => {
                  itemRefs.current[i] = el;
                }}
                role="option"
                aria-selected={c.name === value}
                onMouseDown={(e) => {
                  e.preventDefault();
                  select(c.name);
                }}
                onMouseEnter={() => setHighlighted(i)}
                className={`px-3 py-1.5 cursor-pointer ${i === highlighted ? classes.highlighted : classes.item}`}
              >
                {c.flag} {c.displayName}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
