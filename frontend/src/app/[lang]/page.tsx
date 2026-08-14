import { notFound } from "next/navigation";
import BookingWidget from "@/components/BookingWidget";
import MobileBookingReveal from "@/components/MobileBookingReveal";
import PhotoHoverBadge from "@/components/PhotoHoverBadge";
import ScrollHint from "@/components/ScrollHint";
import SiteHeader from "@/components/SiteHeader";
import SiteFooter from "@/components/SiteFooter";
import { imageUrl, listImagesByLabel, type ImageAsset } from "@/lib/api";
import { getDictionary, hasLocale } from "./dictionaries";

export default async function Home({
  params,
}: {
  params: Promise<{ lang: string }>;
}) {
  const { lang } = await params;
  if (!hasLocale(lang)) notFound();

  const dict = await getDictionary(lang);

  // Admin-managed via the "background" label (Photos panel) rather than a
  // static asset — swapping the photo there updates the live site with no
  // frontend rebuild. `cache: "no-store"` is what makes that true: it opts
  // this page out of static generation/ISR staleness for this fetch.
  const backgroundImages = await listImagesByLabel("background", { cache: "no-store" }).catch(() => []);
  const backgroundImage = backgroundImages[0] ?? null;

  // Photos to show when hovering feature badges, admin-managed via labels
  // (same pattern as the "background" label above) — one label per badge.
  const [bedroomImages, bathroomImages, viewImages, kitchenImages] = await Promise.all([
    listImagesByLabel("bedroom", { cache: "no-store" }).catch(() => []),
    listImagesByLabel("bathroom", { cache: "no-store" }).catch(() => []),
    listImagesByLabel("view", { cache: "no-store" }).catch(() => []),
    listImagesByLabel("kitchen", { cache: "no-store" }).catch(() => []),
  ]);

  const HOVER_IMAGES: Partial<Record<string, ImageAsset[]>> = {
    bedrooms: bedroomImages,
    bathrooms: bathroomImages,
    view: viewImages,
    kitchen: kitchenImages,
  };

  const HOVER_MAX_PHOTOS: Partial<Record<string, number>> = {
    kitchen: 1,
  };

  const FEATURES = [
    { id: "bedrooms", icon: "🛏", label: dict.hero.features.bedrooms },
    { id: "bathrooms", icon: "🚿", label: dict.hero.features.bathrooms },
    { id: "guests", icon: "👥", label: dict.hero.features.guests },
    { id: "view", icon: "🏔", label: dict.hero.features.view },
    { id: "wifi", icon: "📶", label: dict.hero.features.wifi },
    { id: "parking", icon: "🅿️", label: dict.hero.features.parking },
    { id: "kitchen", icon: "🍳", label: dict.hero.features.kitchen },
  ];

  const HIGHLIGHTS = [
    { icon: "🚂", ...dict.highlights.zurich },
    { icon: "⛷️", ...dict.highlights.ski },
    { icon: "🏖", ...dict.highlights.beach },
  ];

  return (
    <div>
      {/* ── FIXED BACKGROUND ────────────────────────────── */}
      <div className="fixed inset-0 -z-10 bg-gray-800">
        {backgroundImage && (
          // eslint-disable-next-line @next/next/no-img-element -- backend-served, not a Next-optimizable local/static asset
          <img
            src={imageUrl(backgroundImage.key)}
            alt={backgroundImage.alt || "Apartment view with Lake Walensee and mountains"}
            className="w-full h-full object-cover object-center"
          />
        )}
        <div
          className="absolute inset-0"
          style={{ background: "rgba(30,30,30,0.30)" }}
        />
      </div>

      {/* ── FULL-VIEWPORT CONTENT ───────────────────────── */}
      <div className="relative z-10 h-dvh flex flex-col overflow-hidden">

      {/* ── NAV ─────────────────────────────────────────── */}
      <SiteHeader lang={lang} dict={dict} />

      {/* ── SCROLLABLE CONTENT ──────────────────────────── */}
      {/* `relative` makes this the containing block for BookingWidget's
          calendar-open breakout (position:absolute) — so a tall calendar
          grows this container's own scrollable area instead of being
          clipped or needing its own separate internal scroll. */}
      <div id="page-scroll" className="flex-1 overflow-y-auto relative">
      <div className="min-h-full flex flex-col">

      {/* ── HERO ────────────────────────────────────────── */}
      <div className="shrink-0">
        <div className="max-w-7xl mx-auto px-6 py-6 lg:py-8">
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_480px] gap-1 lg:gap-12 items-start">
            {/* Left — apartment info */}
            <div className="text-white">
              <div className="flex flex-wrap items-center gap-2 mb-4">
                <span className="flex items-center gap-1.5 bg-white/20 backdrop-blur-sm text-white text-xs font-medium px-3 py-1.5 rounded-full">
                  <span>📍</span>
                  <span>{dict.hero.location}</span>
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
              <div className="hidden sm:flex flex-wrap gap-2">
                {FEATURES.map((f) => {
                  const images = HOVER_IMAGES[f.id];
                  return images ? (
                    <PhotoHoverBadge
                      key={f.id}
                      icon={f.icon}
                      label={f.label}
                      images={images}
                      maxPhotos={HOVER_MAX_PHOTOS[f.id] ?? 2}
                    />
                  ) : (
                    <span
                      key={f.id}
                      className="flex items-center gap-1.5 bg-white/15 backdrop-blur-sm px-3 py-1.5 rounded-full text-sm text-white"
                    >
                      <span>{f.icon}</span>
                      <span>{f.label}</span>
                    </span>
                  );
                })}
              </div>

            </div>

            {/* Right — booking widget */}
            <div>
              <MobileBookingReveal>
                <BookingWidget dict={dict.booking} lang={lang} />
              </MobileBookingReveal>
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

      <ScrollHint label={dict.hero.scrollHint} />

      {/* ── FOOTER ──────────────────────────────────────── */}
      <SiteFooter dict={dict} />
      </div>{/* end full-viewport content */}
    </div>
  );
}
