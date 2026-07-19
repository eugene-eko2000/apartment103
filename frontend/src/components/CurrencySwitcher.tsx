"use client";

import { useEffect, useRef, useState } from "react";
import { currencies } from "@/lib/currency-config";
import { useCurrency } from "@/lib/currency-context";

export default function CurrencySwitcher({ expandOnClick = false }: { expandOnClick?: boolean }) {
  const { currency, setCurrency } = useCurrency();
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

  return (
    <div
      className="relative"
      ref={rootRef}
      onMouseEnter={expandOnClick ? undefined : () => setIsOpen(true)}
      onMouseLeave={expandOnClick ? undefined : () => setIsOpen(false)}
    >
      <button
        type="button"
        onClick={expandOnClick ? () => setIsOpen((v) => !v) : undefined}
        className="flex items-center gap-1 hover:text-teal-700 dark:hover:text-teal-400 transition-colors cursor-pointer"
        aria-label="Change currency"
        aria-expanded={isOpen}
      >
        <span>{currency}</span>
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
          <path d="M1.5 3.5L5 7l3.5-3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full pt-2 z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-100 dark:border-gray-700 py-1 min-w-[100px]">
            {currencies.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => {
                  setCurrency(c);
                  setIsOpen(false);
                }}
                className={`w-full text-left px-4 py-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 ${
                  c === currency ? "text-teal-700 dark:text-teal-400 font-medium" : "text-gray-600 dark:text-gray-300"
                }`}
              >
                {c}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
