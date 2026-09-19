"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import AmenitiesOverlay from "@/components/AmenitiesOverlay";
import LocationOverlay from "@/components/LocationOverlay";
import PhotoGallery from "@/components/PhotoGallery";
import type { Dictionary } from "@/app/[lang]/dictionaries";
import type { Locale } from "@/lib/i18n-config";

/** The full-screen views that sit above the page. Only ever one at a time:
 *  the amenities and location views re-render the site header, so a nav item
 *  owning its own open flag would stack a second view on top of the first
 *  instead of replacing it — and neither would then be reachable to close. */
export type OverlayView = "gallery" | "amenities" | "location";

const OverlayContext = createContext<{
  active: OverlayView | null;
  /** Opens `view`, closing whichever view is open. */
  open: (view: OverlayView) => void;
  close: () => void;
  /** Same, except that asking for the view already open closes it — what the
   *  header nav item does, so the slot that opened a view also dismisses it. */
  toggle: (view: OverlayView) => void;
}>({ active: null, open: () => {}, close: () => {}, toggle: () => {} });

export function useOverlay() {
  return useContext(OverlayContext);
}

export function OverlayProvider({
  lang,
  dict,
  children,
}: {
  lang: Locale;
  dict: Dictionary;
  children: React.ReactNode;
}) {
  const [active, setActive] = useState<OverlayView | null>(null);

  const value = useMemo(
    () => ({
      active,
      open: (view: OverlayView) => setActive(view),
      close: () => setActive(null),
      toggle: (view: OverlayView) => setActive((current) => (current === view ? null : view)),
    }),
    [active],
  );

  /** Kept here rather than inside each view, and keyed on "is anything open"
   *  rather than on which one: swapping views leaves the lock untouched,
   *  where per-view effects would release and re-take it in one commit and
   *  let the page behind flash its scrollbar back. */
  const locked = active !== null;
  useEffect(() => {
    if (!locked) return;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    document.body.style.overflow = "hidden";
    document.body.style.paddingRight = `${scrollbarWidth}px`;
    return () => {
      document.body.style.overflow = "";
      document.body.style.paddingRight = "";
    };
  }, [locked]);

  return (
    <OverlayContext.Provider value={value}>
      {children}
      {active === "gallery" && <PhotoGallery dict={dict.gallery} onClose={value.close} />}
      {active === "amenities" && <AmenitiesOverlay lang={lang} dict={dict} onClose={value.close} />}
      {active === "location" && <LocationOverlay lang={lang} dict={dict} onClose={value.close} />}
    </OverlayContext.Provider>
  );
}
