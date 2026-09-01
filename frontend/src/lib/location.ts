/** Static geography for the Location view.
 *
 *  Everything here describes one fixed apartment, so it lives in code rather
 *  than the backend: the coordinates never change, and the driving figures are
 *  road distances that a routing API would only re-derive on every page view.
 *  Names/descriptions are *not* here — those are per-locale and come from
 *  `dict.location.pois[id]`, keyed by the `id` below.
 */

export type LatLng = { lat: number; lng: number };

/** The groups the nearby list is broken into, in the order they are shown.
 *  Each id is a key into `dict.location.categories` — keep the two in sync.
 *  `groceries` and `transport` are the practical tail of the list: the stops a
 *  guest needs at some point but would not call an outing — where the food
 *  comes from, and how they get in and out of the valley. */
export const POI_CATEGORIES = [
  "beaches",
  "restaurants",
  "skiResorts",
  "hiking",
  "spa",
  "landmarks",
  "nature",
  "cities",
  "groceries",
  "transport",
] as const;

export type PoiCategory = (typeof POI_CATEGORIES)[number];

export type Poi = LatLng & {
  /** Key into `dict.location.pois` — keep the two in sync when editing. */
  id: string;
  icon: string;
  /** The group the POI is listed under; see `POI_CATEGORIES`. */
  category: PoiCategory;
  /** Road distance from the apartment in km (not straight-line) — the distance
   *  across the water on a boat-only POI, which has no road distance to give. */
  distanceKm: number;
  /** Typical walking time in minutes, for the POIs a guest could plausibly
   *  reach on foot. Omitted where the walk runs into hours and the car is the
   *  only realistic way there — `travelModeFor` reads an absent value as
   *  "not walkable". */
  walkMinutes?: number;
} & (
  | {
      /** Typical driving time in minutes. */
      driveMinutes: number;
      boatMinutes?: undefined;
    }
  | {
      driveMinutes?: undefined;
      /** Minutes on the Walensee boat. Carried instead of `driveMinutes` by the
       *  places no road reaches: Quinten is car-free, so a drive time there
       *  would describe a journey a guest cannot make. Where this is set it is
       *  the only figure `travelTimeFor` will report. */
      boatMinutes: number;
    }
);

/** The apartment itself — the map's PIN and the origin of every drive below.
 *  Currently the centre of Unterterzen; replace with the building's own
 *  coordinates to place the pin exactly. Both the map and every directions
 *  link read from this one value. */
export const APARTMENT: LatLng = { lat: 47.11491, lng: 9.25606 };

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
  { id: "marina", category: "restaurants", icon: "⚓", lat: 47.115752, lng: 9.256112, distanceKm: 0.1, driveMinutes: 1, walkMinutes: 2 },
  { id: "ferry", category: "transport", icon: "⛴", lat: 47.114484, lng: 9.253446, distanceKm: 0.4, driveMinutes: 1, walkMinutes: 4 },
  { id: "beach", category: "beaches", icon: "🏖", lat: 47.115333, lng: 9.254743, distanceKm: 0.5, driveMinutes: 2, walkMinutes: 5 },
  { id: "supermarket", category: "groceries", icon: "🛒", lat: 47.11272, lng: 9.24995, distanceKm: 0.5, driveMinutes: 1, walkMinutes: 4 },
  { id: "station", category: "transport", icon: "🚉", lat: 47.11382, lng: 9.25500, distanceKm: 0.7, driveMinutes: 2, walkMinutes: 4 },
  { id: "gondola", category: "skiResorts", icon: "🚡", lat: 47.11329, lng: 9.25505, distanceKm: 0.8, driveMinutes: 2, walkMinutes: 4 },
  { id: "schifffahrt", category: "restaurants", icon: "🍽", lat: 47.112459, lng: 9.278640, distanceKm: 1.9, driveMinutes: 4, walkMinutes: 26 },
  { id: "quinten", category: "restaurants", icon: "⛵", lat: 47.129019, lng: 9.215742, distanceKm: 3.4, boatMinutes: 25 },
  { id: "amami", category: "restaurants", icon: "🍣", lat: 47.127684, lng: 9.302843, distanceKm: 5.4, driveMinutes: 9, walkMinutes: 70 },
  { id: "walenstadt", category: "cities", icon: "🏘", lat: 47.12290, lng: 9.31401, distanceKm: 5.7, driveMinutes: 7, walkMinutes: 68 },
  { id: "migros", category: "groceries", icon: "🛒", lat: 47.121949, lng: 9.313598, distanceKm: 5.9, driveMinutes: 8, walkMinutes: 65 },
  { id: "talalpsee", category: "hiking", icon: "🥾", lat: 47.117855, lng: 9.127953, distanceKm: 12, driveMinutes: 14 },
  { id: "murgsee", category: "hiking", icon: "🏞", lat: 47.060224, lng: 9.197971, distanceKm: 12, driveMinutes: 25 },
  { id: "paxmal", category: "landmarks", icon: "🕊", lat: 47.142260, lng: 9.270287, distanceKm: 13, driveMinutes: 17 },
  { id: "weesen", category: "cities", icon: "🏞", lat: 47.136166, lng: 9.103116, distanceKm: 14, driveMinutes: 16 },
  { id: "betlis", category: "hiking", icon: "🥾", lat: 47.135673, lng: 9.145236, distanceKm: 18, driveMinutes: 22 },
  { id: "amden", category: "hiking", icon: "🏔", lat: 47.14963, lng: 9.14112, distanceKm: 19, driveMinutes: 21 },
  { id: "seerenbachfaelle", category: "nature", icon: "💦", lat: 47.138103, lng: 9.164640, distanceKm: 19, driveMinutes: 25 },
  { id: "schlossSargans", category: "restaurants", icon: "🍷", lat: 47.050276, lng: 9.437180, distanceKm: 20, driveMinutes: 21 },
  { id: "sargans", category: "landmarks", icon: "🏰", lat: 47.04995, lng: 9.43767, distanceKm: 20, driveMinutes: 20 },
  { id: "flumserberg", category: "skiResorts", icon: "🎿", lat: 47.09366, lng: 9.28425, distanceKm: 21, driveMinutes: 24 },
  { id: "pizolFiveLakes", category: "hiking", icon: "🏞", lat: 47.028844, lng: 9.432183, distanceKm: 21, driveMinutes: 22 },
  { id: "badragaz", category: "spa", icon: "♨️", lat: 46.99985, lng: 9.50516, distanceKm: 27, driveMinutes: 25 },
  { id: "pizol", category: "skiResorts", icon: "🎿", lat: 47.017469, lng: 9.473343, distanceKm: 27, driveMinutes: 26 },
  { id: "kloentalersee", category: "hiking", icon: "🏞", lat: 47.031510, lng: 9.004900, distanceKm: 29, driveMinutes: 37 },
  { id: "batoeni", category: "nature", icon: "💧", lat: 46.958559, lng: 9.353443, distanceKm: 33, driveMinutes: 37 },
  { id: "vaduz", category: "cities", icon: "🇱🇮", lat: 47.13929, lng: 9.52280, distanceKm: 36, driveMinutes: 30 },
  { id: "braunwald", category: "hiking", icon: "🚡", lat: 46.928184, lng: 9.001828, distanceKm: 41, driveMinutes: 50 },
  { id: "rapperswil", category: "cities", icon: "🌹", lat: 47.22665, lng: 8.81640, distanceKm: 43, driveMinutes: 34 },
  { id: "linthal", category: "hiking", icon: "🏔", lat: 46.879200, lng: 8.979987, distanceKm: 47, driveMinutes: 57 },
  { id: "chaeserrugg", category: "skiResorts", icon: "🎿", lat: 47.194772, lng: 9.309248, distanceKm: 61, driveMinutes: 55 },
  { id: "laax", category: "skiResorts", icon: "🎿", lat: 46.820053, lng: 9.263302, distanceKm: 69, driveMinutes: 55 },
  { id: "zurich", category: "cities", icon: "🏙", lat: 47.37445, lng: 8.54104, distanceKm: 74, driveMinutes: 55 },
  { id: "davos", category: "skiResorts", icon: "🎿", lat: 46.808491, lng: 9.838794, distanceKm: 74, driveMinutes: 68 },
  { id: "airport", category: "transport", icon: "✈️", lat: 47.45061, lng: 8.56185, distanceKm: 85, driveMinutes: 67 },
];

/** The POIs split into their categories: categories in `POI_CATEGORIES` order,
 *  POIs still nearest-first inside each. Categories nothing falls into are
 *  dropped, so the list never shows an empty heading. */
export function poisByCategory(): { category: PoiCategory; pois: Poi[] }[] {
  return POI_CATEGORIES.map((category) => ({
    category,
    pois: POIS.filter((poi) => poi.category === category),
  })).filter((group) => group.pois.length > 0);
}

const coord = ({ lat, lng }: LatLng) => `${lat},${lng}`;

export type TravelMode = "walking" | "driving" | "boat";

/** A guest walks anything within a quarter of an hour and drives the rest —
 *  the cutoff that picks the travel mode for a POI's directions. */
export const WALKABLE_MINUTES = 15;

/** How a guest actually gets to a POI, and how long it takes them: the walk
 *  where the walk is under the cutoff, the drive everywhere else. One function
 *  for both halves so the figure in the list can never disagree with the mode
 *  the map routes in — a row reading "4 min walk" beside a driving route was
 *  exactly the mismatch this replaces. Anything without a `walkMinutes` figure
 *  is hours away on foot, so it drives — unless no road reaches it at all,
 *  in which case the boat is the only answer and comes first. */
export function travelTimeFor(poi: Poi): { mode: TravelMode; minutes: number } {
  // The boat comes first because it is not a preference: a POI carrying
  // `boatMinutes` has no road to it at all, so neither other figure describes
  // a journey a guest could make.
  if (poi.boatMinutes !== undefined) return { mode: "boat", minutes: poi.boatMinutes };
  // Past the boat check the type has narrowed to the road half of `Poi`, so
  // `driveMinutes` is there to fall back on.
  return poi.walkMinutes !== undefined && poi.walkMinutes <= WALKABLE_MINUTES
    ? { mode: "walking", minutes: poi.walkMinutes }
    : { mode: "driving", minutes: poi.driveMinutes };
}

/** The mode to open a POI's route in — the map, the directions panel and the
 *  Google Maps link all pick their mode here. */
export function travelModeFor(poi: Poi): TravelMode {
  return travelTimeFor(poi).mode;
}

/** Google Maps directions, defaulting to "get me to the apartment" by car.
 *  Pass a POI as `to` for the apartment → POI leg the list rows link to; that
 *  leg starts at the apartment and picks its mode with `travelModeFor`. */
export function directionsUrl(to?: Poi): string {
  // Google Maps has no boat mode of its own; the Walensee ferries run on the
  // Swiss public timetable, so transit is where a guest finds their sailing.
  const mode = to ? travelModeFor(to) : "driving";
  const params = new URLSearchParams({
    api: "1",
    travelmode: mode === "boat" ? "transit" : mode,
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

/** A raw metre figure from the Routes API, rendered for the guest. Only a
 *  fallback: Google returns its own localised `distance` text alongside every
 *  route and step, and that is preferred wherever it is present. */
export function formatMeters(meters: number, locale: string): string {
  return meters >= 1000
    ? `${formatDistance(meters / 1000, locale)} km`
    : `${new Intl.NumberFormat(locale).format(Math.round(meters))} m`;
}

/** Same idea for a duration: whole minutes, never rounded down to zero, for
 *  the `{minutes}` slot of a localised template. */
export function minutesFromMillis(millis: number): number {
  return Math.max(1, Math.round(millis / 60000));
}
