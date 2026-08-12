"use client";

import { usePathname } from "next/navigation";
import { useCurrency } from "./currency-context";
import { useLocaleSwitch } from "./use-locale-switch";
import { locales, type Locale } from "./i18n-config";
import type { Currency, Language } from "./api";

export interface GuestPreferences {
  preferred_language?: Language | null;
  preferred_currency?: Currency | null;
}

// Shared by anywhere a logged-in guest's saved preferred_language /
// preferred_currency should become the site's active locale / currency: the
// global session-sync effect (GuestPreferenceSync), the Profile modal's save
// handler, and the booking flow's guest-details save all funnel through this
// so "the guest's profile is authoritative" stays a single rule instead of
// being reimplemented per call site.
export function useApplyGuestPreferences() {
  const pathname = usePathname();
  const firstSegment = pathname.split("/")[1];
  const currentLang = (locales as readonly string[]).includes(firstSegment) ? (firstSegment as Locale) : null;
  const { currency, setCurrency } = useCurrency();
  const switchLocale = useLocaleSwitch();

  return (preferences: GuestPreferences) => {
    if (preferences.preferred_currency && preferences.preferred_currency !== currency) {
      setCurrency(preferences.preferred_currency);
    }
    if (preferences.preferred_language && currentLang && preferences.preferred_language !== currentLang) {
      switchLocale(preferences.preferred_language);
    }
  };
}
