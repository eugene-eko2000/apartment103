import Image from "next/image";
import { notFound } from "next/navigation";
import BookingWidget from "@/components/BookingWidget";
import GalleryButton from "@/components/GalleryButton";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import CurrencySwitcher from "@/components/CurrencySwitcher";
import ThemeSwitcher from "@/components/ThemeSwitcher";
import UserMenu from "@/components/UserMenu";
import { getDictionary, hasLocale } from "./dictionaries";

export default async function Home({
  params,
}: {
  params: Promise<{ lang: string }>;
}) {
  const { lang } = await params;
  if (!hasLocale(lang)) notFound();

  const dict = await getDictionary(lang);

  const FEATURES = [
    { icon: "🛏", label: dict.hero.features.bedrooms },
    { icon: "🚿", label: dict.hero.features.bathrooms },
    { icon: "👥", label: dict.hero.features.guests },
    { icon: "🏔", label: dict.hero.features.view },
    { icon: "📶", label: dict.hero.features.wifi },
    { icon: "🅿️", label: dict.hero.features.parking },
    { icon: "🍳", label: dict.hero.features.kitchen },
  ];

  const HIGHLIGHTS = [
    { icon: "🚂", ...dict.highlights.zurich },
    { icon: "⛷️", ...dict.highlights.ski },
    { icon: "🏖", ...dict.highlights.beach },
  ];

  return (
    <div>
      {/* ── FIXED BACKGROUND ────────────────────────────── */}
      <div className="fixed inset-0 -z-10">
        <Image
          src="/hero2.jpeg"
          alt="Apartment view with Lake Walensee and mountains"
          fill
          priority
          className="object-cover object-center"
        />
        <div
          className="absolute inset-0"
          style={{ background: "rgba(30,30,30,0.30)" }}
        />
      </div>

      {/* ── FULL-VIEWPORT CONTENT ───────────────────────── */}
      <div className="relative z-10 h-screen flex flex-col overflow-hidden">

      {/* ── NAV ─────────────────────────────────────────── */}
      <header className="shrink-0 z-50 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md border-b border-gray-100 dark:border-gray-800 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm font-bold"
              style={{ background: "linear-gradient(135deg, #0f766e, #0891b2)" }}
            >
              103
            </span>
            <span className="font-semibold text-gray-800 dark:text-gray-100">Apartment 103</span>
          </div>
          <nav className="hidden sm:flex items-center gap-6 text-sm text-gray-500 dark:text-gray-400">
            <GalleryButton label={dict.nav.gallery} dict={dict.gallery} />
            <a href="#" className="hover:text-teal-700 dark:hover:text-teal-400 transition-colors">{dict.nav.amenities}</a>
            <a href="#" className="hover:text-teal-700 dark:hover:text-teal-400 transition-colors">{dict.nav.location}</a>
            <a href="#" className="hover:text-teal-700 dark:hover:text-teal-400 transition-colors">{dict.nav.reviews}</a>
            <div className="flex items-center gap-4">
              <LanguageSwitcher currentLang={lang} />
              <CurrencySwitcher />
              <ThemeSwitcher
                labels={{ light: dict.themeSwitcher.light, dark: dict.themeSwitcher.dark, system: dict.themeSwitcher.system }}
                ariaLabel={dict.themeSwitcher.label}
              />
              <UserMenu lang={lang} dict={dict.userMenu} />
            </div>
          </nav>
        </div>
      </header>

      {/* ── SCROLLABLE CONTENT ──────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
      <div className="min-h-full flex flex-col">

      {/* ── HERO ────────────────────────────────────────── */}
      <div className="shrink-0">
        <div className="max-w-7xl mx-auto px-6 py-6 lg:py-8">
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_480px] gap-12 items-start">
            {/* Left — apartment info */}
            <div className="text-white">
              <div className="flex flex-wrap items-center gap-2 mb-4">
                <span className="flex items-center gap-1.5 bg-white/20 backdrop-blur-sm text-white text-xs font-medium px-3 py-1.5 rounded-full">
                  <span>📍</span>
                  <span>{dict.hero.location}</span>
                </span>
                <span className="flex items-center gap-1 bg-amber-400/90 text-amber-900 text-xs font-semibold px-3 py-1.5 rounded-full">
                  {dict.hero.rating}
                </span>
              </div>

              <h1 className="text-4xl lg:text-5xl font-bold leading-tight mb-3">
                {dict.hero.titleLine1}<br />
                <span className="text-cyan-200">{dict.hero.titleLine2}</span>
              </h1>

              <p className="text-lg text-teal-100 mb-6 max-w-md leading-relaxed">
                {dict.hero.description}
              </p>

              {/* Feature tags */}
              <div className="flex flex-wrap gap-2">
                {FEATURES.map((f) => (
                  <span
                    key={f.label}
                    className="flex items-center gap-1.5 bg-white/15 backdrop-blur-sm px-3 py-1.5 rounded-full text-sm text-white"
                  >
                    <span>{f.icon}</span>
                    <span>{f.label}</span>
                  </span>
                ))}
              </div>

            </div>

            {/* Right — booking widget */}
            <div>
              <BookingWidget dict={dict.booking} lang={lang} />
            </div>
          </div>
        </div>
      </div>

      {/* Flexible gap: grows to push highlights toward the footer on tall
          screens, shrinks down to a 1px floor before the page scrolls */}
      <div className="flex-1 min-h-[1px]" />

      {/* ── ABOUT / HIGHLIGHTS ──────────────────────────── */}
      <section className="shrink-0 max-w-7xl mx-auto w-full px-6 pb-4">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {HIGHLIGHTS.map((card) => (
            <div
              key={card.title}
              className="bg-white dark:bg-gray-800 rounded-2xl px-5 py-4 shadow-sm border border-gray-100 dark:border-gray-700 flex items-start gap-3"
            >
              <span className="text-2xl mt-0.5 shrink-0">{card.icon}</span>
              <div>
                <h3 className="font-semibold text-gray-900 dark:text-gray-100 text-sm mb-0.5">{card.title}</h3>
                <p className="text-gray-500 dark:text-gray-400 text-xs leading-relaxed">{card.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      </div>{/* end flex column */}
      </div>{/* end scrollable content */}

      {/* ── FOOTER ──────────────────────────────────────── */}
      <footer className="shrink-0 border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
        <div className="max-w-7xl mx-auto px-6 py-3 flex flex-col sm:flex-row items-center justify-between gap-2 text-sm text-gray-400 dark:text-gray-500">
          <span>{dict.footer.copyright.replace("{year}", String(new Date().getFullYear()))}</span>
          <div className="flex gap-6">
            <a href="#" className="hover:text-teal-700 dark:hover:text-teal-400 transition-colors">{dict.footer.privacy}</a>
            <a href="#" className="hover:text-teal-700 dark:hover:text-teal-400 transition-colors">{dict.footer.terms}</a>
            <a href="#" className="hover:text-teal-700 dark:hover:text-teal-400 transition-colors">{dict.footer.contact}</a>
          </div>
        </div>
      </footer>
      </div>{/* end full-viewport content */}
    </div>
  );
}
