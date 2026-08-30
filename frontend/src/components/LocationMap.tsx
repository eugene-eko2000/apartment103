"use client";

import { useEffect, useRef, useState } from "react";
import { useTheme } from "@/lib/theme-context";
import {
  GOOGLE_MAPS_MAP_ID,
  hasGoogleMapsConfig,
  loadGoogleMaps,
  onGoogleMapsAuthFailure,
} from "@/lib/googleMaps";
import { APARTMENT, DEFAULT_ZOOM, POIS, directionsUrl } from "@/lib/location";

/** Markers are Advanced Markers, whose `content` is ordinary DOM — so the pins
 *  are Tailwind-styled elements rather than sprite images, and they anchor at
 *  their own bottom centre the way a map pin should.
 *
 *  The elements are built once and then mutated in place. Assigning a fresh
 *  element to `marker.content` orphans the previous one while the Maps API
 *  still has its attach queued, which surfaces as an async TypeError from
 *  deep inside marker.js. */
function apartmentContent(label: string): HTMLElement {
  const root = document.createElement("div");
  root.innerHTML =
    `<span class="relative flex h-7 w-7 items-center justify-center">
       <span class="absolute inline-flex h-7 w-7 animate-ping rounded-full bg-teal-500/40"></span>
       <span class="relative inline-flex h-7 w-7 items-center justify-center rounded-full border-2 border-white bg-teal-600 text-xs shadow-lg dark:border-gray-900">🏠</span>
     </span>`;
  root.title = label;
  return root;
}

function poiBadgeClass(active: boolean): string {
  return `flex h-7 w-7 items-center justify-center rounded-full border text-[13px] shadow-sm transition-transform ${
    active
      ? "scale-125 border-teal-500 bg-teal-50 dark:border-teal-400 dark:bg-teal-900"
      : "border-gray-300 bg-white dark:border-gray-600 dark:bg-gray-800"
  }`;
}

/** Returns the wrapper to hand to the marker plus the badge to restyle when
 *  the POI becomes the selected one. */
function poiContent(icon: string): { root: HTMLElement; badge: HTMLElement } {
  const root = document.createElement("div");
  const badge = document.createElement("span");
  badge.textContent = icon;
  badge.className = poiBadgeClass(false);
  root.appendChild(badge);
  return { root, badge };
}

export default function LocationMap({
  activePoiId,
  onSelectPoi,
  labels,
  poiNames,
}: {
  /** POI the list has focused, or null for "showing the apartment". */
  activePoiId: string | null;
  onSelectPoi: (id: string | null) => void;
  labels: {
    apartment: string;
    recenter: string;
    mapHint: string;
    unavailable: string;
    openInMaps: string;
  };
  poiNames: Record<string, string>;
}) {
  const { resolvedTheme } = useTheme();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<google.maps.Map | null>(null);
  const poiMarkersRef = useRef<Map<string, google.maps.marker.AdvancedMarkerElement>>(new Map());
  const apartmentMarkerRef = useRef<google.maps.marker.AdvancedMarkerElement | null>(null);
  /** The badge span inside each POI marker, restyled on selection. */
  const poiBadgesRef = useRef<Map<string, HTMLElement>>(new Map());
  const directionsServiceRef = useRef<google.maps.DirectionsService | null>(null);
  const directionsRendererRef = useRef<google.maps.DirectionsRenderer | null>(null);

  const [mapReady, setMapReady] = useState(false);
  const [failed, setFailed] = useState(!hasGoogleMapsConfig);

  // Latest props for the build effect, which must not re-run on every render.
  const onSelectPoiRef = useRef(onSelectPoi);
  const poiNamesRef = useRef(poiNames);
  const apartmentLabelRef = useRef(labels.apartment);
  useEffect(() => {
    onSelectPoiRef.current = onSelectPoi;
    poiNamesRef.current = poiNames;
    apartmentLabelRef.current = labels.apartment;
  });

  // A key Google rejects still "loads", so this is the only way to catch a
  // bad key or a domain missing from the referrer allowlist and show the
  // fallback rather than Google's error panel.
  useEffect(() => onGoogleMapsAuthFailure(() => setFailed(true)), []);

  // The map is rebuilt when the theme flips because `colorScheme`, like
  // `mapId`, "can only be set when the map is initialized" — there is no
  // setter to switch a live map between the light and dark cartography.
  useEffect(() => {
    if (!hasGoogleMapsConfig) return;

    let cancelled = false;
    const poiMarkers = poiMarkersRef.current;
    const poiBadges = poiBadgesRef.current;

    (async () => {
      try {
        await loadGoogleMaps();
        const [{ Map }, { AdvancedMarkerElement }, core, routes] = await Promise.all([
          google.maps.importLibrary("maps") as Promise<google.maps.MapsLibrary>,
          google.maps.importLibrary("marker") as Promise<google.maps.MarkerLibrary>,
          google.maps.importLibrary("core") as Promise<google.maps.CoreLibrary>,
          google.maps.importLibrary("routes") as Promise<google.maps.RoutesLibrary>,
        ]);
        if (cancelled || !containerRef.current) return;

        const map = new Map(containerRef.current, {
          center: APARTMENT,
          zoom: DEFAULT_ZOOM,
          mapId: GOOGLE_MAPS_MAP_ID,
          colorScheme:
            resolvedTheme === "dark" ? core.ColorScheme.DARK : core.ColorScheme.LIGHT,
          // "cooperative" keeps a plain wheel scroll scrolling the page and
          // asks for ctrl/⌘+scroll (or two fingers) to zoom — the map sits
          // inside a scrolling overlay and would otherwise swallow it.
          gestureHandling: "cooperative",
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: true,
          zoomControl: true,
        });

        apartmentMarkerRef.current = new AdvancedMarkerElement({
          map,
          position: APARTMENT,
          content: apartmentContent(apartmentLabelRef.current),
          title: apartmentLabelRef.current,
          zIndex: 1000,
        });

        for (const poi of POIS) {
          const { root, badge } = poiContent(poi.icon);
          const marker = new AdvancedMarkerElement({
            map,
            position: { lat: poi.lat, lng: poi.lng },
            content: root,
            title: poiNamesRef.current[poi.id] ?? poi.id,
            gmpClickable: true,
          });
          marker.addListener("click", () => onSelectPoiRef.current(poi.id));
          poiMarkers.set(poi.id, marker);
          poiBadges.set(poi.id, badge);
        }

        directionsServiceRef.current = new routes.DirectionsService();
        directionsRendererRef.current = new routes.DirectionsRenderer({
          map,
          // The apartment and the POI already have their own pins; Google's
          // default A/B markers would just stack on top of them.
          suppressMarkers: true,
          preserveViewport: false,
          polylineOptions: { strokeColor: "#0d9488", strokeOpacity: 0.9, strokeWeight: 5 },
        });

        mapRef.current = map;
        setMapReady(true);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
      // Detaching runs through the Maps API's own setters, which throw if the
      // map never finished initialising (a rejected key leaves it half-built).
      // A failed teardown must not take the page down with it, so each step is
      // best-effort: the map and markers are being discarded either way.
      try {
        directionsRendererRef.current?.setMap(null);
        // Every marker has to be detached before the map goes, including the
        // apartment's: a marker left pointing at a torn-down map keeps async
        // work queued inside the Maps API and throws when it finally runs
        // (StrictMode's double mount and the dark-mode rebuild both hit this).
        for (const marker of poiMarkers.values()) marker.map = null;
        if (apartmentMarkerRef.current) apartmentMarkerRef.current.map = null;
      } catch {
        // Already broken — nothing left to clean up on the Google side.
      }
      directionsRendererRef.current = null;
      directionsServiceRef.current = null;
      poiMarkers.clear();
      poiBadges.clear();
      apartmentMarkerRef.current = null;
      mapRef.current = null;
      setMapReady(false);
    };
  }, [resolvedTheme]);

  // Selecting a POI draws the real driving route from the apartment to it and
  // frames that route; clearing the selection returns to the apartment.
  useEffect(() => {
    // `failed` matters as well as the refs: an auth failure swaps in the
    // fallback without re-running the build effect, so the refs below still
    // hold Maps objects that are no longer usable.
    if (failed) return;
    const map = mapRef.current;
    const renderer = directionsRendererRef.current;
    const service = directionsServiceRef.current;
    if (!map || !renderer || !service) return;

    for (const poi of POIS) {
      const badge = poiBadgesRef.current.get(poi.id);
      if (badge) badge.className = poiBadgeClass(poi.id === activePoiId);
    }

    let stale = false;
    const target = POIS.find((p) => p.id === activePoiId);

    /** Frame the apartment and the POI together — used when there is no route
     *  to draw, either because none was requested or the request failed. */
    const frameBoth = (to: { lat: number; lng: number }) => {
      const bounds = new google.maps.LatLngBounds();
      bounds.extend(APARTMENT);
      bounds.extend(to);
      map.fitBounds(bounds, 60);
    };

    // Every call here goes through the Maps API, which throws synchronously on
    // a map that failed to initialise. Nothing in this effect is worth
    // crashing the whole Location view for.
    try {
      if (!target) {
        renderer.set("directions", null);
        map.panTo(APARTMENT);
        map.setZoom(DEFAULT_ZOOM);
        return;
      }

      const to = { lat: target.lat, lng: target.lng };
      // route() returns a promise only on a healthy service; a rejected key
      // can hand back undefined instead, which must not be chained onto.
      const pending = service.route({
        origin: APARTMENT,
        destination: to,
        travelMode: google.maps.TravelMode.DRIVING,
      });

      if (!pending?.then) {
        frameBoth(to);
        return;
      }

      pending
        .then((result) => {
          if (!stale) renderer.setDirections(result);
        })
        .catch(() => {
          // The Directions API may not be enabled on the key — the route line
          // is a bonus, so fall back to simply framing the two points.
          if (stale) return;
          try {
            renderer.set("directions", null);
            frameBoth(to);
          } catch {
            // Map is gone; the selection simply shows no route.
          }
        });
    } catch {
      // Same reasoning as above: leave the map as it is rather than throwing.
    }

    return () => {
      stale = true;
    };
  }, [activePoiId, mapReady, failed]);

  if (failed) {
    // No key, no Map ID, or the API refused to load — the view still has to
    // work, so hand the guest straight to Google Maps instead.
    return (
      <div className="rounded-2xl border border-dashed border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800/50 px-6 py-10 text-center">
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{labels.unavailable}</p>
        <a
          href={directionsUrl()}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-lg border border-gray-300 dark:border-gray-600 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 hover:text-teal-700 dark:hover:text-teal-400 transition-colors"
        >
          {labels.openInMaps}
        </a>
      </div>
    );
  }

  return (
    <div className="relative">
      <div
        // Keyed on the theme so a rebuild gets a brand-new node: the Maps API
        // has no destroy(), and hand-clearing a reused container pulls the DOM
        // out from under work it still has queued.
        key={resolvedTheme}
        ref={containerRef}
        data-testid="location-map"
        className="h-[320px] sm:h-[420px] w-full rounded-2xl border border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 overflow-hidden"
      />
      <button
        type="button"
        onClick={() => onSelectPoi(null)}
        className="absolute top-3 left-3 z-10 rounded-lg bg-white/90 dark:bg-gray-800/90 backdrop-blur px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-200 shadow-sm border border-gray-200 dark:border-gray-600 hover:text-teal-700 dark:hover:text-teal-400 transition-colors cursor-pointer"
      >
        {labels.recenter}
      </button>
      <p className="mt-2 text-xs text-gray-400 dark:text-gray-500">{labels.mapHint}</p>
    </div>
  );
}
