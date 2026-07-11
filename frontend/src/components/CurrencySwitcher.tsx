"use client";

import { currencies } from "@/lib/currency-config";
import { useCurrency } from "@/lib/currency-context";

export default function CurrencySwitcher() {
  const { currency, setCurrency } = useCurrency();

  return (
    <div className="relative group">
      <button
        type="button"
        className="flex items-center gap-1 hover:text-teal-700 transition-colors cursor-pointer"
        aria-label="Change currency"
      >
        <span>{currency}</span>
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
          <path d="M1.5 3.5L5 7l3.5-3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      <div className="absolute right-0 top-full pt-2 hidden group-hover:block z-50">
        <div className="bg-white rounded-xl shadow-lg border border-gray-100 py-1 min-w-[100px]">
          {currencies.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCurrency(c)}
              className={`w-full text-left px-4 py-2 text-sm cursor-pointer hover:bg-gray-50 ${
                c === currency ? "text-teal-700 font-medium" : "text-gray-600"
              }`}
            >
              {c}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
