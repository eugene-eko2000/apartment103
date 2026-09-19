"use client";

import { useRouter, usePathname } from "next/navigation";
import { LOCALE_COOKIE, PREFERENCE_COOKIE_DAYS, setCookie } from "@/lib/cookies";
import { useCookieConsent } from "@/lib/cookie-consent-context";
import { preferenceTargets, setSessionLanguage } from "@/lib/session-preferences";
import type { Locale } from "@/lib/i18n-config";

// Shared by LanguageSwitcher (explicit user choice) and any code that needs
// to move the site to a different locale route on a guest's behalf (e.g.
// applying their saved preferred_language after login).
export function useLocaleSwitch() {
  const router = useRouter();
  const pathname = usePathname();
  const { status } = useCookieConsent();

  // `remember: false` is for moving the site to a locale the guest already
  // chose elsewhere (their profile) — there is nothing new to record.
  return (locale: Locale, { remember = true }: { remember?: boolean } = {}) => {
    const segments = pathname.split("/");
    segments[1] = locale;
    if (remember) {
      // Signed in behind a saved preferred_language: the pick is for this
      // page load only, so it neither overwrites the profile nor outlives a
      // reload. Otherwise the cookie is what answers the question on the
      // next visit, so that is where the pick goes (see session-preferences).
      const targets = preferenceTargets("language");
      if (targets.session) setSessionLanguage(locale);
      if (targets.cookie && status === "allowed") setCookie(LOCALE_COOKIE, locale, PREFERENCE_COOKIE_DAYS);
    }
    router.push(segments.join("/") || `/${locale}`);
    router.refresh();
  };
}
