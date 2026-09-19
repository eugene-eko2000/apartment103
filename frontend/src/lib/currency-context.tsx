"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { currencies, defaultCurrency, type Currency } from "@/lib/currency-config";
import { getCookie, setCookie } from "./cookies";
import { useCookieConsent } from "./cookie-consent-context";
import { readGuestSession } from "./guest-auth";
import { getSessionCurrency, setSessionCurrency } from "./session-preferences";

const COOKIE_NAME = "PREFERRED_CURRENCY";

const CurrencyContext = createContext<{
  currency: Currency;
  setCurrency: (currency: Currency, options?: { remember?: boolean }) => void;
}>({
  currency: defaultCurrency,
  setCurrency: () => {},
});

export function CurrencyProvider({ children }: { children: React.ReactNode }) {
  const [currency, setCurrencyState] = useState<Currency>(defaultCurrency);
  const { status } = useCookieConsent();

  useEffect(() => {
    // A signed-in guest's pick from the switcher outranks the cookie, so a
    // remount of this provider mid-session (it lives in the [lang] layout)
    // restores what they chose instead of snapping back to the cookie.
    const override = getSessionCurrency();
    if (override) {
      setCurrencyState(override);
      return;
    }
    const stored = getCookie(COOKIE_NAME);
    if (stored && (currencies as readonly string[]).includes(stored)) {
      setCurrencyState(stored as Currency);
    }
  }, []);

  // `remember: false` is for adopting a currency the guest already chose
  // elsewhere (their profile) — there is nothing new to record.
  const setCurrency = (next: Currency, { remember = true }: { remember?: boolean } = {}) => {
    setCurrencyState(next);
    if (!remember) return;
    if (readGuestSession()) {
      // Signed in: keep the pick for this page load only, so it neither
      // overwrites the profile nor outlives a reload (session-preferences).
      setSessionCurrency(next);
    } else if (status === "allowed") {
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
