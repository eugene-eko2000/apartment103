"use client";

import { useId } from "react";
import { TONE_CLASSES, type FieldTone } from "@/components/field-chrome";

/* A short list picker — preferred language, preferred currency — as a plain
 * <select>, wearing the same palette as the CountrySelect it stands beside in
 * the guest's "Your data" grid.
 */
export function SelectField({
  label,
  value,
  options,
  noneLabel,
  onChange,
  tone = "booking",
  valid = false,
}: {
  label: string;
  value: string;
  options: string[];
  /** Shown, in placeholder grey, while nothing is chosen; also the first option. */
  noneLabel: string;
  onChange: (v: string) => void;
  tone?: FieldTone;
  valid?: boolean;
}) {
  const id = useId();
  const classes = TONE_CLASSES[tone];

  return (
    <div>
      <label htmlFor={id} className={`block text-xs font-medium mb-1 ${classes.label}`}>
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`w-full px-3 py-2 text-sm border focus:outline-none focus:ring-1 cursor-pointer ${
          valid ? classes.validField : classes.field
        } ${value ? classes.text : classes.empty}`}
      >
        {/* The blank choice is an option like any other, so clearing the
            preference takes the same click as setting one. */}
        <option value="">{noneLabel}</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}
