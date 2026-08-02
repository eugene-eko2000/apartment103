"use client";

import { useEffect, useRef, useState } from "react";
import { locales, localeNames, localeFlags, type Locale } from "@/lib/i18n-config";
import { useLocaleSwitch } from "@/lib/use-locale-switch";

export default function LanguageSwitcher({
  currentLang,
  expandOnClick = false,
}: {
  currentLang: Locale;
  expandOnClick?: boolean;
}) {
  const switchLocale = useLocaleSwitch();
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!expandOnClick || !isOpen) return;
    const handler = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setIsOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [expandOnClick, isOpen]);

  const switchTo = (locale: Locale) => {
    if (locale === currentLang) return;
    switchLocale(locale);
  };

  return (
    <div className={`relative ${expandOnClick ? "" : "group"}`} ref={rootRef}>
      <button
        type="button"
        onClick={expandOnClick ? () => setIsOpen((v) => !v) : undefined}
        className="flex items-center gap-1 hover:text-teal-700 dark:hover:text-teal-400 transition-colors cursor-pointer"
        aria-label="Change language"
        aria-expanded={expandOnClick ? isOpen : undefined}
      >
        <span aria-hidden="true">{localeFlags[currentLang]}</span>
        <span>{currentLang.toUpperCase()}</span>
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
          <path d="M1.5 3.5L5 7l3.5-3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      <div
        className={`absolute right-0 top-full pt-2 z-50 ${
          expandOnClick ? (isOpen ? "" : "hidden") : "hidden group-hover:block"
        }`}
      >
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-100 dark:border-gray-700 py-1 min-w-[140px]">
          {locales.map((locale) => (
            <button
              key={locale}
              type="button"
              onClick={() => {
                switchTo(locale);
                setIsOpen(false);
              }}
              className={`w-full flex items-center gap-2.5 text-left px-4 py-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 ${
                locale === currentLang ? "text-teal-700 dark:text-teal-400 font-medium" : "text-gray-600 dark:text-gray-300"
              }`}
            >
              <span className="text-base leading-none" aria-hidden="true">{localeFlags[locale]}</span>
              <span>{localeNames[locale]}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
