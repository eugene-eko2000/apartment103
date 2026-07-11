"use client";

import { useRouter, usePathname } from "next/navigation";
import { locales, localeNames, localeFlags, type Locale } from "@/lib/i18n-config";
import { setCookie } from "@/lib/cookies";
import { useCookieConsent } from "@/lib/cookie-consent-context";

export default function LanguageSwitcher({ currentLang }: { currentLang: Locale }) {
  const router = useRouter();
  const pathname = usePathname();
  const { status } = useCookieConsent();

  const switchTo = (locale: Locale) => {
    if (locale === currentLang) return;
    const segments = pathname.split("/");
    segments[1] = locale;
    if (status === "allowed") {
      setCookie("NEXT_LOCALE", locale, 365);
    }
    router.push(segments.join("/") || `/${locale}`);
    router.refresh();
  };

  return (
    <div className="relative group">
      <button
        type="button"
        className="flex items-center gap-1 hover:text-teal-700 transition-colors cursor-pointer"
        aria-label="Change language"
      >
        <span aria-hidden="true">{localeFlags[currentLang]}</span>
        <span>{currentLang.toUpperCase()}</span>
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
          <path d="M1.5 3.5L5 7l3.5-3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      <div className="absolute right-0 top-full pt-2 hidden group-hover:block z-50">
        <div className="bg-white rounded-xl shadow-lg border border-gray-100 py-1 min-w-[140px]">
          {locales.map((locale) => (
            <button
              key={locale}
              type="button"
              onClick={() => switchTo(locale)}
              className={`w-full flex items-center gap-2.5 text-left px-4 py-2 text-sm cursor-pointer hover:bg-gray-50 ${
                locale === currentLang ? "text-teal-700 font-medium" : "text-gray-600"
              }`}
            >
              <span className="text-base leading-none" aria-hidden="true">{localeFlags[locale]}</span>
              <span>{localeNames[locale]}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
