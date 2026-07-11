"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { currencies, defaultCurrency, type Currency } from "@/lib/currency-config";
import { getCookie, setCookie } from "./cookies";
import { useCookieConsent } from "./cookie-consent-context";

const COOKIE_NAME = "PREFERRED_CURRENCY";

const CurrencyContext = createContext<{
  currency: Currency;
  setCurrency: (currency: Currency) => void;
}>({
  currency: defaultCurrency,
  setCurrency: () => {},
});

export function CurrencyProvider({ children }: { children: React.ReactNode }) {
  const [currency, setCurrencyState] = useState<Currency>(defaultCurrency);
  const { status } = useCookieConsent();

  useEffect(() => {
    const stored = getCookie(COOKIE_NAME);
    if (stored && (currencies as readonly string[]).includes(stored)) {
      setCurrencyState(stored as Currency);
    }
  }, []);

  const setCurrency = (next: Currency) => {
    setCurrencyState(next);
    if (status === "allowed") {
      setCookie(COOKIE_NAME, next, 365);
    }
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
