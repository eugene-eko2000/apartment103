"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import SiteHeader from "./SiteHeader";
import SiteFooter from "./SiteFooter";
import LocationMap from "./LocationMap";
import { POIS, directionsUrl, formatDistance, poisByCategory } from "@/lib/location";
import type { Dictionary } from "@/app/[lang]/dictionaries";
import type { Locale } from "@/lib/i18n-config";

export default function LocationOverlay({
  lang,
  dict,
  onClose,
}: {
  lang: Locale;
  dict: Dictionary;
  onClose: () => void;
}) {
  const l = dict.location;
  const [activePoiId, setActivePoiId] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    document.body.style.overflow = "hidden";
    document.body.style.paddingRight = `${scrollbarWidth}px`;
    return () => {
      document.body.style.overflow = "";
      document.body.style.paddingRight = "";
    };
  }, []);

  const poiNames = Object.fromEntries(POIS.map((p) => [p.id, l.pois[p.id as keyof typeof l.pois].name]));

  return createPortal(
    <div className="fixed inset-0 z-50 flex flex-col bg-gray-50/75 dark:bg-gray-950/80 backdrop-blur-md">
      {/* Same layering trick as the amenities view: the header's "Location"
          nav slot closes this layer rather than stacking another one. */}
      <SiteHeader lang={lang} dict={dict} onCloseLocation={onClose} />

      <div className="relative flex-1 min-h-0">
        <button
          onClick={onClose}
          aria-label={l.backHome}
          className="absolute top-5 right-6 sm:top-8 sm:right-12 z-10 text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-200 transition-colors text-3xl sm:text-5xl leading-none cursor-pointer"
        >
          ✕
        </button>

        <div className="h-full overflow-y-auto">
          <div className="max-w-5xl mx-auto px-6 py-10">
            <h1 className="text-3xl lg:text-4xl font-bold text-gray-900 dark:text-gray-100 mb-2">{l.pageTitle}</h1>
            <p className="text-gray-500 dark:text-gray-400 mb-6">{l.subtitle}</p>

            {/* ── MAP ─────────────────────────────────────── */}
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-4 sm:p-5 mb-8">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                <p className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
                  <span aria-hidden="true">📍</span>
                  <span className="font-medium text-gray-900 dark:text-gray-100">{l.address}</span>
                </p>
                <a
                  href={directionsUrl()}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 rounded-lg bg-teal-600 hover:bg-teal-700 dark:bg-teal-500 dark:hover:bg-teal-400 text-white dark:text-teal-950 text-sm font-medium px-4 py-2 transition-colors"
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path d="M8 1.5 14.5 8 8 14.5 1.5 8 8 1.5Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                    <path d="M6 9.5v-2a1.5 1.5 0 0 1 1.5-1.5H10M8.5 4.5 10 6 8.5 7.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  {l.directions}
                </a>
              </div>

              <LocationMap
                activePoiId={activePoiId}
                onSelectPoi={setActivePoiId}
                labels={{
                  apartment: l.apartmentMarker,
                  recenter: l.recenter,
                  mapHint: l.mapHint,
                  unavailable: l.mapUnavailable,
                  openInMaps: l.openInMaps,
                }}
                poiNames={poiNames}
              />
            </div>

            {/* ── NEARBY POIs ─────────────────────────────── */}
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-1">{l.nearbyTitle}</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{l.nearbySubtitle}</p>

            {/* One card per category, in POI_CATEGORIES order; inside a card
                the POIs stay nearest-first. */}
            <div className="space-y-6">
              {poisByCategory().map(({ category, pois }) => (
                <section key={category}>
                  <h3 className="px-1 mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    {l.categories[category]}
                  </h3>
                  <ul className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-700 overflow-hidden">
                    {pois.map((poi) => {
                      const text = l.pois[poi.id as keyof typeof l.pois];
                      const active = poi.id === activePoiId;
                      return (
                        <li key={poi.id}>
                          <div
                            className={`flex items-center gap-4 px-4 sm:px-5 py-3 transition-colors ${
                              active ? "bg-teal-50 dark:bg-teal-900/30" : "hover:bg-gray-50 dark:hover:bg-gray-700/40"
                            }`}
                          >
                            {/* The row itself is the "show on map" control — the
                                directions link beside it stays a real anchor so it
                                can still be opened in a new tab. */}
                            <button
                              type="button"
                              onClick={() => setActivePoiId(active ? null : poi.id)}
                              aria-pressed={active}
                              aria-label={`${text.name} — ${l.showOnMap}`}
                              className="flex flex-1 items-center gap-4 text-left cursor-pointer"
                            >
                              <span aria-hidden="true" className="text-xl shrink-0 w-7 text-center">{poi.icon}</span>
                              <span className="min-w-0 flex-1">
                                <span className="block text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{text.name}</span>
                                <span className="block text-xs text-gray-500 dark:text-gray-400 truncate">{text.desc}</span>
                              </span>
                              <span className="shrink-0 text-right">
                                <span className="block text-sm font-semibold text-gray-900 dark:text-gray-100 tabular-nums">
                                  {formatDistance(poi.distanceKm, lang)} {l.distanceUnit}
                                </span>
                                <span className="block text-xs text-gray-500 dark:text-gray-400 tabular-nums">
                                  {l.driveTime.replace("{minutes}", String(poi.driveMinutes))}
                                </span>
                              </span>
                            </button>
                            <a
                              href={directionsUrl(poi)}
                              target="_blank"
                              rel="noopener noreferrer"
                              aria-label={`${l.directions} — ${text.name}`}
                              title={l.directions}
                              className="shrink-0 text-gray-400 dark:text-gray-500 hover:text-teal-700 dark:hover:text-teal-400 transition-colors"
                            >
                              <svg width="18" height="18" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                                <path d="M8 1.5 14.5 8 8 14.5 1.5 8 8 1.5Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                                <path d="M6 9.5v-2a1.5 1.5 0 0 1 1.5-1.5H10M8.5 4.5 10 6 8.5 7.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                            </a>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              ))}
            </div>

            <p className="mt-4 text-xs text-gray-400 dark:text-gray-500">{l.disclaimer}</p>
          </div>
        </div>
      </div>

      <SiteFooter dict={dict} />
    </div>,
    document.body
  );
}
