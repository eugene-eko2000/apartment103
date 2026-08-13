import Link from "next/link";
import GalleryButton from "@/components/GalleryButton";
import AmenitiesButton from "@/components/AmenitiesButton";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import CurrencySwitcher from "@/components/CurrencySwitcher";
import ThemeSwitcher from "@/components/ThemeSwitcher";
import UserMenu from "@/components/UserMenu";
import MobileMenu from "@/components/MobileMenu";
import type { Dictionary } from "@/app/[lang]/dictionaries";
import type { Locale } from "@/lib/i18n-config";

export default function SiteHeader({
  lang,
  dict,
  onCloseAmenities,
}: {
  lang: Locale;
  dict: Dictionary;
  /** Rendered inside the amenities layer itself — swaps the nav item that
   *  would normally open the layer for one that closes it, instead of
   *  stacking a second layer on top of the first. */
  onCloseAmenities?: () => void;
}) {
  const amenitiesLinkClass = "hover:text-teal-700 dark:hover:text-teal-400 transition-colors cursor-pointer";
  const amenitiesActiveClass = "text-teal-700 dark:text-teal-400 font-medium";

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
          <GalleryButton label={dict.nav.gallery} dict={dict.gallery} />
          {onCloseAmenities ? (
            <button onClick={onCloseAmenities} className={`${amenitiesLinkClass} ${amenitiesActiveClass}`}>{dict.nav.amenities}</button>
          ) : (
            <AmenitiesButton label={dict.nav.amenities} lang={lang} dict={dict} />
          )}
          <a href="#" className="hover:text-teal-700 dark:hover:text-teal-400 transition-colors">{dict.nav.location}</a>
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
          <GalleryButton label={dict.nav.gallery} dict={dict.gallery} className="py-3" />
          {onCloseAmenities ? (
            <button onClick={onCloseAmenities} className={`py-3 ${amenitiesLinkClass} ${amenitiesActiveClass}`}>{dict.nav.amenities}</button>
          ) : (
            <AmenitiesButton label={dict.nav.amenities} lang={lang} dict={dict} className="py-3" />
          )}
          <a href="#" className="py-3 hover:text-teal-700 dark:hover:text-teal-400 transition-colors">{dict.nav.location}</a>
          <div className="flex items-center gap-5 pt-4 mt-1 border-t border-gray-100 dark:border-gray-700">
            <LanguageSwitcher currentLang={lang} expandOnClick />
            <CurrencySwitcher expandOnClick />
            <ThemeSwitcher
              labels={{ light: dict.themeSwitcher.light, dark: dict.themeSwitcher.dark, system: dict.themeSwitcher.system }}
              ariaLabel={dict.themeSwitcher.label}
              expandOnClick
            />
            <UserMenu dict={dict.userMenu} lang={lang} />
          </div>
        </MobileMenu>
      </div>
    </header>
  );
}
