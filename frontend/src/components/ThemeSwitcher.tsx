"use client";

import { useState } from "react";
import { useTheme, type Theme } from "@/lib/theme-context";

const OPTIONS: Theme[] = ["light", "dark", "system"];

const DEFAULT_LABELS: Record<Theme, string> = {
  light: "Light",
  dark: "Dark",
  system: "System",
};

export default function ThemeSwitcher({
  labels = DEFAULT_LABELS,
  ariaLabel = "Change theme",
}: {
  labels?: Record<Theme, string>;
  ariaLabel?: string;
}) {
  const { theme, setTheme } = useTheme();
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div
      className="relative"
      onMouseEnter={() => setIsOpen(true)}
      onMouseLeave={() => setIsOpen(false)}
    >
      <button
        type="button"
        className="flex items-center gap-1 hover:text-teal-700 dark:hover:text-teal-400 transition-colors cursor-pointer"
        aria-label={ariaLabel}
        aria-expanded={isOpen}
      >
        {/* Sun / moon glyph driven purely by CSS so it never flashes on hydration */}
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="dark:hidden">
          <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="2" />
          <path
            d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="hidden dark:block">
          <path
            d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinejoin="round"
          />
        </svg>
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
          <path d="M1.5 3.5L5 7l3.5-3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full pt-2 z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-100 dark:border-gray-700 py-1 min-w-[120px]">
            {OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => {
                  setTheme(option);
                  setIsOpen(false);
                }}
                className={`w-full text-left px-4 py-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 ${
                  option === theme ? "text-teal-700 dark:text-teal-400 font-medium" : "text-gray-600 dark:text-gray-300"
                }`}
              >
                {labels[option]}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
