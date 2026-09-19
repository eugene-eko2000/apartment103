"use client";

import { readGuestSession } from "./guest-auth";
import type { Currency } from "./currency-config";
import type { Locale } from "./i18n-config";

// Where a pick made from the header's language / currency switchers should
// be recorded, and what the site should believe about a logged-in guest's
// own saved settings.
//
// Two cases, split by what the guest saved on their profile:
//
//   * The profile names a language / currency. The header switchers then
//     only give a temporary override: it must not touch preferred_language /
//     preferred_currency, and it must not be written to the anonymous
//     NEXT_LOCALE / PREFERRED_CURRENCY cookies either — reloading the site
//     has to bring the guest's own saved settings back.
//
//   * The profile leaves the field at "No Preference" (null). Nothing on the
//     account can answer the question, so the cookies are authoritative for
//     a logged-in guest exactly as they are for an anonymous one, and the
//     switchers write them. Otherwise the pick would die with the page load.
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

// null while nobody has told us what the signed-in guest saved — the
// profile fetch is still in flight, or there is no session at all.
let profilePreferences: { language: Locale | null; currency: Currency | null } | null = null;

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

export function setProfilePreferences(preferences: {
  language?: Locale | null;
  currency?: Currency | null;
}): void {
  profilePreferences = {
    language: preferences.language ?? null,
    currency: preferences.currency ?? null,
  };
}

// True only once we know the profile names one — "not loaded yet" is not
// the same answer as "No Preference", and the two are treated differently
// by preferenceTargets below.
export function hasProfileLanguage(): boolean {
  return !!profilePreferences?.language;
}

export function hasProfileCurrency(): boolean {
  return !!profilePreferences?.currency;
}

// Decides what a header switcher does with a fresh pick. `session` keeps it
// for this page load, `cookie` persists it.
//
// The both-at-once case is the window between mount and the profile fetch
// landing: we cannot yet tell which of the two rules applies, so we do
// both. Writing the cookie is what makes the pick survive a reload if the
// profile turns out to say "No Preference"; the session override is what
// stops the arriving profile from yanking the guest back if it turns out to
// name a setting. Whichever way it lands, the loser is inert — an override
// equal to the active value changes nothing, and a cookie is only read when
// the profile has nothing to say.
export function preferenceTargets(field: "language" | "currency"): {
  session: boolean;
  cookie: boolean;
} {
  if (!readGuestSession()) return { session: false, cookie: true };
  const saved = field === "language" ? hasProfileLanguage() : hasProfileCurrency();
  return { session: !profilePreferences || saved, cookie: !saved };
}

// Called when the guest's own settings become authoritative again: they
// saved their profile, or they signed out and the cookies take over. Drops
// what we knew about the profile too — on sign-out it is stale, and on a
// save the caller replaces it with the freshly returned guest.
export function clearSessionPreferences(): void {
  sessionLanguage = null;
  sessionCurrency = null;
  profilePreferences = null;
}
