"use client";

import type { Currency } from "./currency-config";
import type { Locale } from "./i18n-config";

// A logged-in guest may still use the header's language / currency
// switchers, but their pick is only a temporary override: it must not touch
// the preferred_language / preferred_currency they saved on their profile,
// and it must not be written to the anonymous NEXT_LOCALE /
// PREFERRED_CURRENCY cookies either — reloading the site has to bring their
// own saved settings back. (Logged out, nothing changes: the switchers keep
// writing the cookies.)
//
// Module scope rather than React state, for two reasons. The override has
// to be readable from the places that would otherwise undo it — the locale
// switch (a route change) and the profile sync, which re-runs on every
// guest-session change, e.g. a login in another tab — without threading
// state through them. And module scope has exactly the right lifetime: it
// survives client-side navigation and dies with the page load, so a reload
// hands the guest back their own settings.

let sessionLanguage: Locale | null = null;
let sessionCurrency: Currency | null = null;

export function getSessionLanguage(): Locale | null {
  return sessionLanguage;
}

export function getSessionCurrency(): Currency | null {
  return sessionCurrency;
}

export function setSessionLanguage(locale: Locale): void {
  sessionLanguage = locale;
}

export function setSessionCurrency(currency: Currency): void {
  sessionCurrency = currency;
}

// Called when the guest's own settings become authoritative again: they
// saved their profile, or they signed out and the cookies take over.
export function clearSessionPreferences(): void {
  sessionLanguage = null;
  sessionCurrency = null;
}
