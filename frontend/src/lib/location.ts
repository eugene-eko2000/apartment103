/** Static geography for the Location view.
 *
 *  Everything here describes one fixed apartment, so it lives in code rather
 *  than the backend: the coordinates never change, and the driving figures are
 *  road distances that a routing API would only re-derive on every page view.
 *  Names/descriptions are *not* here — those are per-locale and come from
 *  `dict.location.pois[id]`, keyed by the `id` below.
 */

export type LatLng = { lat: number; lng: number };

export type Poi = LatLng & {
  /** Key into `dict.location.pois` — keep the two in sync when editing. */
  id: string;
  icon: string;
  /** Road distance from the apartment in km (not straight-line). */
  distanceKm: number;
  /** Typical driving time in minutes. */
  driveMinutes: number;
  /** Typical walking time in minutes, for the POIs a guest could plausibly
   *  reach on foot. Omitted where the walk runs into hours and the car is the
   *  only realistic way there — `travelModeFor` reads an absent value as
   *  "not walkable". */
  walkMinutes?: number;
};

/** The apartment itself — the map's PIN and the origin of every drive below.
 *  Currently the centre of Unterterzen; replace with the building's own
 *  coordinates to place the pin exactly. Both the map and every directions
 *  link read from this one value. */
export const APARTMENT: LatLng = { lat: 47.11395, lng: 9.25229 };

/** Zoom that fits the village and the lake shore around it. */
export const DEFAULT_ZOOM = 14;

/** Sorted nearest-first — the list under the map renders them in this order.
 *  Coordinates come from OpenStreetMap; the km/minutes are real car routes
 *  from APARTMENT, measured with OSRM rather than estimated from the
 *  straight-line distance, which the lake and the mountains make useless
 *  here. `walkMinutes` comes from the same tool's foot profile, which follows
 *  footpaths the car route cannot use (and vice versa), so it is a separate
 *  measurement rather than the drive scaled down. Re-measure them if
 *  APARTMENT moves. */
export const POIS: Poi[] = [
  { id: "beach", icon: "🏖", lat: 47.11518, lng: 9.25473, distanceKm: 0.5, driveMinutes: 2, walkMinutes: 5 },
  { id: "supermarket", icon: "🛒", lat: 47.11272, lng: 9.24995, distanceKm: 0.5, driveMinutes: 1, walkMinutes: 4 },
  { id: "station", icon: "🚉", lat: 47.11382, lng: 9.25500, distanceKm: 0.7, driveMinutes: 2, walkMinutes: 4 },
  { id: "gondola", icon: "🚡", lat: 47.11329, lng: 9.25505, distanceKm: 0.8, driveMinutes: 2, walkMinutes: 4 },
  { id: "murg", icon: "🥾", lat: 47.11313, lng: 9.21505, distanceKm: 3.2, driveMinutes: 4, walkMinutes: 40 },
  { id: "walenstadt", icon: "🏘", lat: 47.12290, lng: 9.31401, distanceKm: 5.7, driveMinutes: 7, walkMinutes: 68 },
  { id: "amden", icon: "🏔", lat: 47.14963, lng: 9.14112, distanceKm: 19, driveMinutes: 21 },
  { id: "sargans", icon: "🏰", lat: 47.04995, lng: 9.43767, distanceKm: 20, driveMinutes: 20 },
  { id: "flumserberg", icon: "🎿", lat: 47.09366, lng: 9.28425, distanceKm: 21, driveMinutes: 24 },
  { id: "badragaz", icon: "♨️", lat: 46.99985, lng: 9.50516, distanceKm: 27, driveMinutes: 25 },
  { id: "vaduz", icon: "🇱🇮", lat: 47.13929, lng: 9.52280, distanceKm: 36, driveMinutes: 30 },
  { id: "rapperswil", icon: "🌹", lat: 47.22665, lng: 8.81640, distanceKm: 43, driveMinutes: 34 },
  { id: "zurich", icon: "🏙", lat: 47.37445, lng: 8.54104, distanceKm: 74, driveMinutes: 55 },
  { id: "airport", icon: "✈️", lat: 47.45061, lng: 8.56185, distanceKm: 85, driveMinutes: 67 },
];

const coord = ({ lat, lng }: LatLng) => `${lat},${lng}`;

/** A guest walks anything within a quarter of an hour and drives the rest —
 *  the cutoff that picks the travel mode for a POI's directions. */
export const WALKABLE_MINUTES = 15;

/** The mode to open a POI's route in. Anything without a `walkMinutes` figure
 *  is hours away on foot, so it drives. */
export function travelModeFor(poi: Poi): "walking" | "driving" {
  return poi.walkMinutes !== undefined && poi.walkMinutes <= WALKABLE_MINUTES
    ? "walking"
    : "driving";
}

/** Google Maps directions, defaulting to "get me to the apartment" by car.
 *  Pass a POI as `to` for the apartment → POI leg the list rows link to; that
 *  leg starts at the apartment and picks its mode with `travelModeFor`. */
export function directionsUrl(to?: Poi): string {
  const params = new URLSearchParams({
    api: "1",
    travelmode: to ? travelModeFor(to) : "driving",
  });
  if (to) {
    params.set("origin", coord(APARTMENT));
    params.set("destination", coord(to));
  } else {
    params.set("destination", coord(APARTMENT));
  }
  return `https://www.google.com/maps/dir/?${params}`;
}

/** Distances are stored in km; en/de/fr/it all use metric, so the locale only
 *  decides the decimal separator and whether a sub-km value keeps its digit. */
export function formatDistance(km: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: km < 10 ? 1 : 0,
    maximumFractionDigits: km < 10 ? 1 : 0,
  }).format(km);
}
