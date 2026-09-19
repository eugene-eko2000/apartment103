import Link from "next/link";
import GalleryButton from "@/components/GalleryButton";
import AmenitiesButton from "@/components/AmenitiesButton";
import LocationButton from "@/components/LocationButton";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import CurrencySwitcher from "@/components/CurrencySwitcher";
import ThemeSwitcher from "@/components/ThemeSwitcher";
import UserMenu from "@/components/UserMenu";
import MobileMenu from "@/components/MobileMenu";
import type { Dictionary } from "@/app/[lang]/dictionaries";
import type { Locale } from "@/lib/i18n-config";

/* Rendered by the homepage and again inside each full-screen view, so the
 * nav is the same row wherever the guest is. Which view is open lives in the
 * overlay context, not here: the nav items read it themselves, which is what
 * lets the item for the open view close it instead of stacking a second one. */
export default function SiteHeader({
  lang,
  dict,
}: {
  lang: Locale;
  dict: Dictionary;
}) {
  return (
    <header className="shrink-0 z-50 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md border-b border-gray-100 dark:border-gray-800 shadow-sm">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link href={`/${lang}`} className="flex items-center gap-2">
          {/* eslint-disable-next-line @next/next/no-img-element -- .ico isn't supported by next/image's optimizer */}
          <img
            src="/favicon.ico"
            alt="Berg See Home"
            width={32}
            height={32}
            className="w-8 h-8 rounded-lg"
          />
          <span className="font-semibold text-gray-800 dark:text-gray-100">Berg See Home</span>
        </Link>
        <nav className="hidden sm:flex items-center gap-6 text-sm text-gray-500 dark:text-gray-400">
          <GalleryButton label={dict.nav.gallery} />
          <AmenitiesButton label={dict.nav.amenities} />
          <LocationButton label={dict.nav.location} />
          <div className="flex items-center gap-4">
            <LanguageSwitcher currentLang={lang} />
            <CurrencySwitcher />
            <ThemeSwitcher
              labels={{ light: dict.themeSwitcher.light, dark: dict.themeSwitcher.dark, system: dict.themeSwitcher.system }}
              ariaLabel={dict.themeSwitcher.label}
            />
            <UserMenu dict={dict.userMenu} lang={lang} />
          </div>
        </nav>
        <MobileMenu ariaLabel={dict.nav.menu}>
          <GalleryButton label={dict.nav.gallery} className="py-3" />
          <AmenitiesButton label={dict.nav.amenities} className="py-3" />
          <LocationButton label={dict.nav.location} className="py-3" />
          <UserMenu dict={dict.userMenu} lang={lang} inline />
          <div className="flex items-center gap-5 pt-3 pb-1">
            <LanguageSwitcher currentLang={lang} expandOnClick />
            <CurrencySwitcher expandOnClick />
            <ThemeSwitcher
              labels={{ light: dict.themeSwitcher.light, dark: dict.themeSwitcher.dark, system: dict.themeSwitcher.system }}
              ariaLabel={dict.themeSwitcher.label}
              expandOnClick
            />
          </div>
        </MobileMenu>
      </div>
    </header>
  );
}
