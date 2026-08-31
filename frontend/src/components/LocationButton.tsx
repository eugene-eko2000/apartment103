"use client";

import { useState, type ReactNode } from "react";
import LocationOverlay from "./LocationOverlay";
import type { Dictionary } from "@/app/[lang]/dictionaries";
import type { Locale } from "@/lib/i18n-config";

const NAV_CLASS =
  "text-left hover:text-teal-700 dark:hover:text-teal-400 transition-colors cursor-pointer";

export default function LocationButton({
  label,
  lang,
  dict,
  className = "",
  /** "nav" wears the header link styling; "plain" leaves all styling to
   *  `className`, for callers with their own look (e.g. the hero pill). */
  variant = "nav",
}: {
  label: ReactNode;
  lang: Locale;
  dict: Dictionary;
  className?: string;
  variant?: "nav" | "plain";
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className={variant === "nav" ? `${NAV_CLASS} ${className}` : className}
      >
        {label}
      </button>
      {open && <LocationOverlay lang={lang} dict={dict} onClose={() => setOpen(false)} />}
    </>
  );
}
