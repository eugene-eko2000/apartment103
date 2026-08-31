"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useTheme } from "@/lib/theme-context";
import {
  GOOGLE_MAPS_MAP_ID,
  hasGoogleMapsConfig,
  loadGoogleMaps,
  onGoogleMapsAuthFailure,
} from "@/lib/googleMaps";
import {
  APARTMENT,
  DEFAULT_ZOOM,
  POIS,
  directionsUrl,
  formatMeters,
  minutesFromMillis,
  travelModeFor,
  type LatLng,
  type TravelMode,
} from "@/lib/location";

/** What the map is currently showing.
 *
 *  `directions` on a POI is the step list the row's arrow opens — the row
 *  itself only draws the line, which is the lighter "where is this?" gesture. */
export type MapView =
  | { kind: "apartment" }
  | { kind: "poi"; id: string; directions: boolean };

/** `note` is the second line Google appends to some instructions ("Restricted
 *  usage road", "Destination will be on the right") — a genuine second thought
 *  rather than part of the turn, and unreadable run onto the end of it. */
type Step = { instruction: string; note: string | null; distance: string };

/** The leg to draw: where from, where to, how, and whether the guest asked for
 *  the written steps as well as the line. `key` is the whole of that as one
 *  string — what an answer is tagged with, so that identity is compared on the
 *  leg itself rather than on which render happened to build the object. */
type RouteRequest = {
  key: string;
  origin: LatLng;
  destination: LatLng;
  mode: TravelMode;
  withSteps: boolean;
};

function routeKey(
  origin: LatLng,
  destination: LatLng,
  mode: TravelMode,
  withSteps: boolean,
): string {
  return `${mode}|${origin.lat},${origin.lng}|${destination.lat},${destination.lng}|${withSteps}`;
}

/** The panel's contents. `null` means no panel at all — the map is either
 *  idle or drawing a line nobody asked for directions about. */
type Directions =
  | { status: "loading" }
  | { status: "failed" }
  | { status: "ready"; mode: TravelMode; distance: string; duration: string; steps: Step[] };

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

/** The site's teal, for the route line. */
const ROUTE_COLOR = "#0d9488";

/** The route line, styled from the mode *we* asked for rather than from what
 *  Google inferred. `createPolylines` only knows a section's travel mode when
 *  the response carries `legs`, which is only requested when the directions
 *  panel is open — so the same walk came back dotted from the panel's arrow
 *  and solid from a tap on the POI, one leg drawn two different ways. Deciding
 *  it here makes a walk dotted and a drive solid however the guest got there.
 *
 *  Called only from inside the drawing effect, so `google.maps` is loaded by
 *  the time the symbol below is read. */
function routePolylineStyle(mode: TravelMode) {
  return (defaults: google.maps.PolylineOptions): google.maps.PolylineOptions => ({
    ...defaults,
    strokeColor: ROUTE_COLOR,
    // Both branches set everything the other touches: Google's own dotted
    // styling left in `defaults` would otherwise bead a solid drive, and its
    // transparent stroke would leave a walk with no line under the dots.
    ...(mode === "walking"
      ? {
          // A dotted line is a fully transparent stroke with a circle repeated
          // along it — any stroke left visible shows through the gaps.
          strokeOpacity: 0,
          icons: [
            {
              icon: {
                path: google.maps.SymbolPath.CIRCLE,
                fillColor: ROUTE_COLOR,
                fillOpacity: 1,
                strokeColor: ROUTE_COLOR,
                strokeOpacity: 1,
                scale: 3.5,
              },
              offset: "0",
              repeat: "12px",
            },
          ],
        }
      : { strokeOpacity: 1, icons: [] }),
  });
}

/** Takes the route's lines off the map. Detaching is the only teardown a
 *  Polyline has, and it has to happen before the map itself goes. */
function detachPolylines(polylines: google.maps.Polyline[]): void {
  for (const polyline of polylines) polyline.setMap(null);
}

/** Turns a computed route into the panel's contents. Google returns its own
 *  localised text for every figure; `locale` is only used for the fallback
 *  when a response arrives without it. */
function readDirections(
  route: google.maps.routes.Route,
  mode: TravelMode,
  locale: string,
  minutesLabel: string,
): Directions {
  const minutes = (millis: number) =>
    minutesLabel.replace("{minutes}", String(minutesFromMillis(millis)));

  const steps: Step[] = (route.legs?.[0]?.steps ?? [])
    .map((step) => {
      const [instruction = "", ...rest] = (step.instructions ?? "").split("\n");
      return {
        instruction,
        note: rest.join(" ") || null,
        distance: step.localizedValues?.distance ?? formatMeters(step.distanceMeters, locale),
      };
    })
    // A step with nothing to say ("depart", on some routes) is noise in a list
    // the guest reads top to bottom.
    .filter((step) => step.instruction !== "");

  return {
    status: "ready",
    mode,
    distance:
      route.localizedValues?.distance ??
      (route.distanceMeters !== undefined ? formatMeters(route.distanceMeters, locale) : "—"),
    duration:
      route.localizedValues?.duration ??
      (route.durationMillis != null ? minutes(route.durationMillis) : "—"),
    steps,
  };
}

export default function LocationMap({
  view,
  onSelectPoi,
  onHideDirections,
  locale,
  labels,
  poiNames,
}: {
  view: MapView;
  onSelectPoi: (id: string | null) => void;
  /** Closes the step list without losing the line the guest is looking at. */
  onHideDirections: () => void;
  /** BCP-47 tag the route's instructions are asked for in. */
  locale: string;
  labels: {
    apartment: string;
    recenter: string;
    mapHint: string;
    unavailable: string;
    openInMaps: string;
    directions: string;
    fromApartment: string;
    loading: string;
    routeFailed: string;
    hide: string;
    driving: string;
    walking: string;
    minutes: string;
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
  /** The last answer Google gave, tagged with the leg it answers. Tagging is
   *  what lets the panel be derived rather than set: a result whose tag is no
   *  longer the current leg is simply a result for a question nobody is
   *  asking, and the panel falls back to "loading" on its own. */
  const [routeResult, setRouteResult] = useState<{ key: string; value: Directions } | null>(null);

  const activeId = view.kind === "poi" ? view.id : null;
  const panelOpen = view.kind === "poi" && view.directions;

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

  /** The leg to draw, or null when the map is just showing the apartment. */
  const request = useMemo((): RouteRequest | null => {
    if (view.kind === "poi") {
      const poi = POIS.find((p) => p.id === view.id);
      if (!poi) return null;
      const destination = { lat: poi.lat, lng: poi.lng };
      const mode = travelModeFor(poi);
      return {
        key: routeKey(APARTMENT, destination, mode, view.directions),
        origin: APARTMENT,
        destination,
        mode,
        withSteps: view.directions,
      };
    }
    return null;
  }, [view]);

  // Drawing the current leg: the real route from origin to destination, framed
  // to fit, plus — when the guest asked for directions rather than just "show
  // me where this is" — the turn-by-turn list under the map.
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
      if (badge) badge.className = poiBadgeClass(poi.id === activeId);
    }

    let stale = false;

    /** Frame the two ends together — used when there is no route to draw,
     *  either because none was requested or the request failed. */
    const frameBoth = (from: LatLng, to: LatLng) => {
      const bounds = new google.maps.LatLngBounds();
      bounds.extend(from);
      bounds.extend(to);
      map.fitBounds(bounds, 60);
    };

    // Every call here goes through the Maps API, which throws synchronously on
    // a map that failed to initialise. Nothing in this effect is worth
    // crashing the whole Location view for.
    try {
      detachPolylines(routePolylinesRef.current);
      routePolylinesRef.current = [];

      if (!request) {
        map.panTo(APARTMENT);
        map.setZoom(DEFAULT_ZOOM);
        return;
      }

      const { key, origin, destination, mode, withSteps } = request;

      // computeRoutes() returns a promise only on a healthy library; a rejected
      // key can hand back undefined instead, which must not be chained onto.
      const computing = Route.computeRoutes({
        origin,
        destination,
        // The field mask is mandatory, and asking for only what is used keeps
        // the response small: `path` is the line, `viewport` is Google's own
        // framing for it, and the rest is the panel — requested only when the
        // panel is open. `legs` carries the steps and their own localised text.
        fields: withSteps
          ? ["path", "viewport", "legs", "localizedValues", "distanceMeters", "durationMillis"]
          : ["path", "viewport"],
        travelMode: mode === "walking" ? "WALKING" : "DRIVING",
        // Instructions come back written in the guest's own language, and in
        // the units the country they are standing in actually uses.
        language: locale,
        region: "CH",
        units: google.maps.UnitSystem.METRIC,
      });

      // computeRoutes() returns a promise only on a healthy library; a rejected
      // key can hand back undefined instead. Turning that into a rejection
      // rather than an early return keeps every outcome on one path — and
      // keeps the panel's state out of this effect's synchronous body.
      const pending =
        typeof (computing as { then?: unknown } | undefined)?.then === "function"
          ? computing
          : Promise.reject<Awaited<typeof computing>>(
              new Error("The routes library is not usable."),
            );

      pending
        .then(({ routes }) => {
          if (stale) return;
          const route = routes?.[0];
          // Drawing happens a tick later than the checks above, so it needs
          // the same guard as the synchronous part: the map may be gone.
          try {
            if (!route) {
              frameBoth(origin, destination);
              setRouteResult({ key, value: { status: "failed" } });
              return;
            }
            // Only the line is drawn: both ends already have their own pins,
            // and createWaypointAdvancedMarkers() would stack Google's A/B
            // markers on top of them.
            const polylines = route.createPolylines({ polylineOptions: routePolylineStyle(mode) });
            for (const polyline of polylines) polyline.setMap(map);
            routePolylinesRef.current = polylines;

            // Replaces the old renderer's preserveViewport: false.
            if (route.viewport) map.fitBounds(route.viewport, 60);
            else frameBoth(origin, destination);

            if (withSteps) {
              setRouteResult({ key, value: readDirections(route, mode, locale, labels.minutes) });
            }
          } catch {
            // Map is gone; the selection simply shows no route.
          }
        })
        .catch(() => {
          // The Routes API may not be enabled on the key. The line is a bonus,
          // so fall back to framing the two points — but the step list is the
          // whole point of the panel, so that says so plainly.
          if (stale) return;
          setRouteResult({ key, value: { status: "failed" } });
          try {
            frameBoth(origin, destination);
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
    // `labels` and `locale` are read on every run but never worth re-routing
    // for on their own — a language switch re-mounts the overlay anyway.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request?.key, request, activeId, view.kind, mapReady, failed]);

  // The panel is open from the moment the guest asks for directions, through
  // Google still answering, to there being something to read. Its contents are
  // derived rather than stored: anything but a fresh answer to the leg on
  // screen reads as "still working on it".
  const directions: Directions | null = !panelOpen
    ? null
    : routeResult && request && routeResult.key === request.key
      ? routeResult.value
      : { status: "loading" };

  // A Directions press from far down the nearby list would otherwise answer
  // off-screen: the panel opens against a map the guest has scrolled past. The
  // whole widget is brought into view, and `nearest` makes that a no-op when it
  // already is — a marker click must not yank the page around.
  //
  // Keyed on which route was asked for, not merely on the panel being open:
  // pressing Directions on a second POI while the first one's panel is still up
  // is the same gesture from the same place in the list, and needs the same
  // answer brought back into view.
  const panelKey = panelOpen && view.kind === "poi" ? `poi:${view.id}` : null;
  const widgetRef = useRef<HTMLDivElement | null>(null);
  const shownPanelKey = useRef<string | null>(null);
  useEffect(() => {
    if (panelKey !== null && panelKey !== shownPanelKey.current) {
      widgetRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    shownPanelKey.current = panelKey;
  }, [panelKey]);

  /** Google Maps itself, for the cases the in-page route cannot cover. */
  const fallbackUrl =
    view.kind === "poi" ? directionsUrl(POIS.find((p) => p.id === view.id)) : directionsUrl();

  if (failed) {
    // No key, no Map ID, or the API refused to load — the view still has to
    // work, so hand the guest straight to Google Maps instead.
    return (
      <div className="rounded-2xl border border-dashed border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800/50 px-6 py-10 text-center">
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{labels.unavailable}</p>
        <a
          href={fallbackUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-lg border border-gray-300 dark:border-gray-600 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 hover:text-teal-700 dark:hover:text-teal-400 transition-colors"
        >
          {labels.openInMaps}
        </a>
      </div>
    );
  }

  const destinationName =
    view.kind === "poi" ? (poiNames[view.id] ?? view.id) : labels.apartment;

  const note = (text: string) => (
    <div className="px-4 pb-4 text-sm text-gray-500 dark:text-gray-400">
      <p>{text}</p>
      <div className="mt-2 flex flex-wrap items-center gap-4 text-xs font-medium">
        <a
          href={fallbackUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-teal-700 dark:text-teal-400 hover:underline"
        >
          {labels.openInMaps}
        </a>
      </div>
    </div>
  );

  return (
    <div className="relative" ref={widgetRef}>
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

      {panelOpen && (
        <section
          data-testid="directions-panel"
          aria-label={labels.directions}
          className="mt-3 rounded-2xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/60 overflow-hidden"
        >
          <div className="flex items-start justify-between gap-3 px-4 pt-3 pb-2">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                {destinationName}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                {labels.fromApartment}
              </p>
            </div>
            <button
              type="button"
              onClick={onHideDirections}
              className="shrink-0 text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-teal-700 dark:hover:text-teal-400 transition-colors cursor-pointer"
            >
              {labels.hide}
            </button>
          </div>

          {directions?.status === "loading" ? (
            <p className="px-4 pb-4 text-sm text-gray-500 dark:text-gray-400">{labels.loading}</p>
          ) : directions?.status === "failed" ? (
            note(labels.routeFailed)
          ) : (
            directions?.status === "ready" && (
                    <>
                      <div className="flex flex-wrap items-center gap-2 px-4 pb-3 text-xs text-gray-600 dark:text-gray-300">
                        <span className="rounded-full bg-teal-600/10 dark:bg-teal-400/15 px-2 py-0.5 font-medium text-teal-700 dark:text-teal-300">
                          {directions.mode === "walking" ? labels.walking : labels.driving}
                        </span>
                        <span className="font-semibold tabular-nums text-gray-900 dark:text-gray-100">
                          {directions.distance}
                        </span>
                        <span aria-hidden="true">·</span>
                        <span className="tabular-nums">{directions.duration}</span>
                      </div>
                      {directions.steps.length > 0 && (
                        <ol className="max-h-56 overflow-y-auto border-t border-gray-200 dark:border-gray-700 divide-y divide-gray-200 dark:divide-gray-700">
                          {directions.steps.map((step, index) => (
                            <li
                              key={index}
                              className="flex items-baseline gap-3 px-4 py-2.5 text-sm text-gray-700 dark:text-gray-200"
                            >
                              <span className="w-4 shrink-0 text-xs tabular-nums text-gray-400 dark:text-gray-500">
                                {index + 1}
                              </span>
                              <span className="flex-1">
                                {step.instruction}
                                {step.note && (
                                  <span className="block text-xs text-gray-500 dark:text-gray-400">
                                    {step.note}
                                  </span>
                                )}
                              </span>
                              <span className="shrink-0 text-xs tabular-nums text-gray-500 dark:text-gray-400">
                                {step.distance}
                              </span>
                            </li>
                          ))}
                        </ol>
                      )}
                    </>
            )
          )}
        </section>
      )}

      <p className="mt-2 text-xs text-gray-400 dark:text-gray-500">{labels.mapHint}</p>
    </div>
  );
}
