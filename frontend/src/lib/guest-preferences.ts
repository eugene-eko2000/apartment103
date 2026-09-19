"use client";

import { usePathname } from "next/navigation";
import { useCurrency } from "./currency-context";
import { useCookieConsent } from "./cookie-consent-context";
import { useLocaleSwitch } from "./use-locale-switch";
import {
  CURRENCY_COOKIE,
  LOCALE_COOKIE,
  PREFERENCE_COOKIE_DAYS,
  setCookie,
} from "./cookies";
import { locales, type Locale } from "./i18n-config";
import {
  clearSessionPreferences,
  getSessionCurrency,
  getSessionLanguage,
  setProfilePreferences,
} from "./session-preferences";
import type { Currency, Language } from "./api";

export interface GuestPreferences {
  preferred_language?: Language | null;
  preferred_currency?: Currency | null;
}

// Shared by anywhere a logged-in guest's saved preferred_language /
// preferred_currency should become the site's active locale / currency: the
// global session-sync effect (GuestPreferenceSync) and the Profile modal's
// save handler both funnel through this so "the guest's profile is
// authoritative" stays a single rule instead of being reimplemented per call
// site. It is also where the profile's answer is recorded for the header
// switchers, which need to know whether they are overriding a saved setting
// or filling in for one the guest left at "No Preference".
//
// One exception to that rule: a pick the guest made from the header
// switchers during this page load wins, so a later run of the sync (it
// re-runs on every guest-session change) does not drag them back to their
// profile settings. `authoritative` marks the call sites where the guest has
// just changed the profile itself, which spends the override.
export function useApplyGuestPreferences() {
  const pathname = usePathname();
  const firstSegment = pathname.split("/")[1];
  const currentLang = (locales as readonly string[]).includes(firstSegment) ? (firstSegment as Locale) : null;
  const { currency, setCurrency } = useCurrency();
  const switchLocale = useLocaleSwitch();
  const { status } = useCookieConsent();

  return (preferences: GuestPreferences, { authoritative = false }: { authoritative?: boolean } = {}) => {
    if (authoritative) clearSessionPreferences();
    setProfilePreferences({
      language: preferences.preferred_language ?? null,
      currency: preferences.preferred_currency ?? null,
    });

    const nextCurrency = getSessionCurrency() ?? preferences.preferred_currency;
    const nextLanguage = getSessionLanguage() ?? preferences.preferred_language;

    if (nextCurrency && nextCurrency !== currency) {
      setCurrency(nextCurrency, { remember: false });
    }
    if (nextLanguage && currentLang && nextLanguage !== currentLang) {
      switchLocale(nextLanguage, { remember: false });
    }

    // The guest has just saved a field as "No Preference", handing the
    // question back to the cookies. Put what they are looking at into them:
    // it is either a header pick that was only being held for this page load
    // (the profile used to name a setting) or the cookie's own value, and
    // without this the save would quietly change the site back on the next
    // reload.
    if (authoritative && status === "allowed") {
      if (!preferences.preferred_currency) {
        setCookie(CURRENCY_COOKIE, currency, PREFERENCE_COOKIE_DAYS);
      }
      if (!preferences.preferred_language && currentLang) {
        setCookie(LOCALE_COOKIE, currentLang, PREFERENCE_COOKIE_DAYS);
      }
    }
  };
}
