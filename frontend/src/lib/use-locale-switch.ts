"use client";

import { useRouter, usePathname } from "next/navigation";
import { setCookie } from "@/lib/cookies";
import { useCookieConsent } from "@/lib/cookie-consent-context";
import type { Locale } from "@/lib/i18n-config";

// Shared by LanguageSwitcher (explicit user choice) and any code that needs
// to move the site to a different locale route on a guest's behalf (e.g.
// applying their saved preferred_language after login).
export function useLocaleSwitch() {
  const router = useRouter();
  const pathname = usePathname();
  const { status } = useCookieConsent();

  return (locale: Locale) => {
    const segments = pathname.split("/");
    segments[1] = locale;
    if (status === "allowed") {
      setCookie("NEXT_LOCALE", locale, 365);
    }
    router.push(segments.join("/") || `/${locale}`);
    router.refresh();
  };
}
