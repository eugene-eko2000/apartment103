"use client";

import { useState } from "react";
import LocationOverlay from "./LocationOverlay";
import type { Dictionary } from "@/app/[lang]/dictionaries";
import type { Locale } from "@/lib/i18n-config";

export default function LocationButton({
  label,
  lang,
  dict,
  className = "",
}: {
  label: string;
  lang: Locale;
  dict: Dictionary;
  className?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className={`text-left hover:text-teal-700 dark:hover:text-teal-400 transition-colors cursor-pointer ${className}`}
      >
        {label}
      </button>
      {open && <LocationOverlay lang={lang} dict={dict} onClose={() => setOpen(false)} />}
    </>
  );
}
