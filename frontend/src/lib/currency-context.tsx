"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { currencies, defaultCurrency, type Currency } from "@/lib/currency-config";

const STORAGE_KEY = "PREFERRED_CURRENCY";

const CurrencyContext = createContext<{
  currency: Currency;
  setCurrency: (currency: Currency) => void;
}>({
  currency: defaultCurrency,
  setCurrency: () => {},
});

export function CurrencyProvider({ children }: { children: React.ReactNode }) {
  const [currency, setCurrencyState] = useState<Currency>(defaultCurrency);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && (currencies as readonly string[]).includes(stored)) {
      setCurrencyState(stored as Currency);
    }
  }, []);

  const setCurrency = (next: Currency) => {
    setCurrencyState(next);
    localStorage.setItem(STORAGE_KEY, next);
  };

  return (
    <CurrencyContext.Provider value={{ currency, setCurrency }}>
      {children}
    </CurrencyContext.Provider>
  );
}

export function useCurrency() {
  return useContext(CurrencyContext);
}
