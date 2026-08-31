"use client";

import { useEffect, useRef, useState } from "react";
import { useTheme } from "@/lib/theme-context";
import {
  GOOGLE_MAPS_MAP_ID,
  hasGoogleMapsConfig,
  loadGoogleMaps,
  onGoogleMapsAuthFailure,
} from "@/lib/googleMaps";
import { APARTMENT, DEFAULT_ZOOM, POIS, directionsUrl, travelModeFor } from "@/lib/location";

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
    `<span class="relative flex h-10 w-10 items-center justify-center">
       <span class="absolute inline-flex h-10 w-10 animate-ping rounded-full bg-teal-500/40"></span>
       <span class="relative inline-flex h-10 w-10 items-center justify-center rounded-full border-2 border-white bg-teal-600 text-base shadow-lg dark:border-gray-900">🏠</span>
     </span>`;
  root.title = label;
  return root;
}

/** Every POI badge stays fully legible — the chosen one is picked out by a
 *  heavier teal edge and a halo ring around it rather than by pushing the
 *  others back, which at map scale just made them hard to find. */
function poiBadgeClass(active: boolean): string {
  return `flex h-7 w-7 items-center justify-center rounded-full text-[13px] transition-all ${
    active
      ? "scale-125 border-2 border-teal-500 bg-teal-50 shadow-md ring-4 ring-teal-500/35 dark:border-teal-400 dark:bg-teal-900 dark:ring-teal-400/35"
      : "border border-gray-300 bg-white shadow-sm dark:border-gray-600 dark:bg-gray-800"
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

/** Takes the route's lines off the map. Detaching is the only teardown a
 *  Polyline has, and it has to happen before the map itself goes. */
function detachPolylines(polylines: google.maps.Polyline[]): void {
  for (const polyline of polylines) polyline.setMap(null);
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
  /** The routes library's `Route` class, captured once the library loads. */
  const routeClassRef = useRef<typeof google.maps.routes.Route | null>(null);
  /** Polylines drawn for the current route, detached when it changes. */
  const routePolylinesRef = useRef<google.maps.Polyline[]>([]);

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
          // "gmp-click" rather than addListener("click", …): an Advanced Marker
          // is a custom element, and the DOM click event is the legacy path it
          // now warns about. `gmpClickable` above is what emits this event.
          marker.addEventListener("gmp-click", () => onSelectPoiRef.current(poi.id));
          poiMarkers.set(poi.id, marker);
          poiBadges.set(poi.id, badge);
        }

        // Route.computeRoutes() is a static call and its polylines are created
        // per result, so there is nothing to construct up front — only the
        // class itself is kept, and only if this build of the API has it.
        routeClassRef.current = routes.Route ?? null;

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
        detachPolylines(routePolylinesRef.current);
        // Every marker has to be detached before the map goes, including the
        // apartment's: a marker left pointing at a torn-down map keeps async
        // work queued inside the Maps API and throws when it finally runs
        // (StrictMode's double mount and the dark-mode rebuild both hit this).
        for (const marker of poiMarkers.values()) marker.map = null;
        if (apartmentMarkerRef.current) apartmentMarkerRef.current.map = null;
      } catch {
        // Already broken — nothing left to clean up on the Google side.
      }
      routePolylinesRef.current = [];
      routeClassRef.current = null;
      poiMarkers.clear();
      poiBadges.clear();
      apartmentMarkerRef.current = null;
      mapRef.current = null;
      setMapReady(false);
    };
  }, [resolvedTheme]);

  // Selecting a POI draws the real route from the apartment to it and frames
  // that route; clearing the selection returns to the apartment. The mode
  // matches the one the row's directions link opens in, so the line on the map
  // and the route Google Maps hands the guest are the same journey.
  useEffect(() => {
    // `failed` matters as well as the refs: an auth failure swaps in the
    // fallback without re-running the build effect, so the refs below still
    // hold Maps objects that are no longer usable.
    if (failed) return;
    const map = mapRef.current;
    const Route = routeClassRef.current;
    if (!map || !Route) return;

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
      detachPolylines(routePolylinesRef.current);
      routePolylinesRef.current = [];

      if (!target) {
        map.panTo(APARTMENT);
        map.setZoom(DEFAULT_ZOOM);
        return;
      }

      const to = { lat: target.lat, lng: target.lng };
      // computeRoutes() returns a promise only on a healthy library; a rejected
      // key can hand back undefined instead, which must not be chained onto.
      const pending = Route.computeRoutes({
        origin: APARTMENT,
        destination: to,
        // The field mask is mandatory, and asking for only what is drawn keeps
        // the response small: `path` is the line, `viewport` is Google's own
        // framing for it.
        fields: ["path", "viewport"],
        travelMode: travelModeFor(target) === "walking" ? "WALKING" : "DRIVING",
      });

      if (!pending?.then) {
        frameBoth(to);
        return;
      }

      pending
        .then(({ routes }) => {
          if (stale) return;
          const route = routes?.[0];
          // Drawing happens a tick later than the checks above, so it needs
          // the same guard as the synchronous part: the map may be gone.
          try {
            if (!route) {
              frameBoth(to);
              return;
            }
            // Only the line is drawn: the apartment and the POI already have
            // their own pins, and createWaypointAdvancedMarkers() would stack
            // Google's A/B markers on top of them.
            const polylines = route.createPolylines({
              polylineOptions: { strokeColor: "#0d9488", strokeOpacity: 0.9, strokeWeight: 5 },
            });
            for (const polyline of polylines) polyline.setMap(map);
            routePolylinesRef.current = polylines;

            // Replaces the old renderer's preserveViewport: false.
            if (route.viewport) map.fitBounds(route.viewport, 60);
            else frameBoth(to);
          } catch {
            // Map is gone; the selection simply shows no route.
          }
        })
        .catch(() => {
          // The Routes API may not be enabled on the key — the route line is a
          // bonus, so fall back to simply framing the two points.
          if (stale) return;
          try {
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
