"use client";

import { useId } from "react";
import RHFPhoneInput from "react-phone-number-input";
import flags from "react-phone-number-input/flags";
import "react-phone-number-input/style.css";
import styles from "./PhoneInput.module.css";

const DEFAULT_COUNTRY = "CH";

export function PhoneInput({
  label,
  value,
  onChange,
  required = true,
  disabled = false,
  tone = "admin",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  disabled?: boolean;
  tone?: "admin" | "booking";
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className={tone === "admin" ? styles.adminLabel : styles.bookingLabel}>
        {label}
      </label>
      <RHFPhoneInput
        id={id}
        className={`${styles.field} ${tone === "admin" ? styles.admin : styles.booking}`}
        flags={flags}
        international
        countryCallingCodeEditable={false}
        defaultCountry={DEFAULT_COUNTRY}
        required={required}
        disabled={disabled}
        value={value || undefined}
        onChange={(v) => onChange(v ?? "")}
      />
    </div>
  );
}
