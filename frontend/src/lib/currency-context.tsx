"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { currencies, defaultCurrency, type Currency } from "@/lib/currency-config";
import { CURRENCY_COOKIE, PREFERENCE_COOKIE_DAYS, getCookie, setCookie } from "./cookies";
import { useCookieConsent } from "./cookie-consent-context";
import { getSessionCurrency, preferenceTargets, setSessionCurrency } from "./session-preferences";

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
    const stored = getCookie(CURRENCY_COOKIE);
    if (stored && (currencies as readonly string[]).includes(stored)) {
      setCurrencyState(stored as Currency);
    }
  }, []);

  // `remember: false` is for adopting a currency the guest already chose
  // elsewhere (their profile) — there is nothing new to record.
  const setCurrency = (next: Currency, { remember = true }: { remember?: boolean } = {}) => {
    setCurrencyState(next);
    if (!remember) return;
    // Signed in behind a saved preferred_currency: the pick is for this page
    // load only, so it neither overwrites the profile nor outlives a reload.
    // Otherwise the cookie is what answers the question on the next visit,
    // so that is where the pick goes (see session-preferences).
    const targets = preferenceTargets("currency");
    if (targets.session) setSessionCurrency(next);
    if (targets.cookie && status === "allowed") setCookie(CURRENCY_COOKIE, next, PREFERENCE_COOKIE_DAYS);
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
