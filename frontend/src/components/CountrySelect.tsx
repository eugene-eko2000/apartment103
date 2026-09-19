"use client";

import { useId, useMemo } from "react";
import { COUNTRIES, localizedCountryName } from "@/lib/countries";
import { TONE_CLASSES, type FieldTone } from "@/components/field-chrome";
import type { Locale } from "@/lib/i18n-config";

/* A plain <select> over the (hardcoded) country list, localized and sorted for
 * the active locale.
 *
 * Option labels are the bare country name, without the flag emoji the list
 * carries: a native select's typeahead matches from the start of the option's
 * text, so a leading flag would make every option begin with the same
 * unreachable character and leave a ~200-entry list with no keyboard way in.
 */
export function CountrySelect({
  label,
  value,
  onChange,
  noneLabel,
  required = true,
  tone = "booking",
  locale = "en",
  valid = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  noneLabel: string;
  required?: boolean;
  tone?: FieldTone;
  locale?: Locale;
  valid?: boolean;
}) {
  const id = useId();
  const classes = TONE_CLASSES[tone];

  // Localized name, sorted for that locale's alphabet — recomputed only when
  // the locale changes.
  const localizedCountries = useMemo(
    () =>
      COUNTRIES.map((c) => ({ name: c.name, displayName: localizedCountryName(c.name, locale) })).sort((a, b) =>
        a.displayName.localeCompare(b.displayName, locale)
      ),
    [locale]
  );

  return (
    <div>
      <label htmlFor={id} className={`block text-xs font-medium mb-1 ${classes.label}`}>
        {label}
      </label>
      <select
        id={id}
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`w-full px-3 py-2 text-sm border focus:outline-none focus:ring-1 cursor-pointer ${
          valid ? classes.validField : classes.field
        } ${value ? classes.text : classes.empty}`}
      >
        {/* Kept selectable rather than disabled, so clearing takes the same
            click as choosing; `required` is what stops an empty submit. */}
        <option value="">{noneLabel}</option>
        {localizedCountries.map((c) => (
          <option key={c.name} value={c.name}>
            {c.displayName}
          </option>
        ))}
      </select>
    </div>
  );
}
