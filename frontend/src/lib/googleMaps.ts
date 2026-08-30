// Loader for the Google Maps JavaScript API.
//
// Google's documented "inline bootstrap loader" is a minified blob meant to be
// pasted into a <script> tag; this is the same contract written out — append
// the API script once, resolve when its callback fires, and from then on pull
// individual libraries with google.maps.importLibrary(). Same lazy
// single-flight shape as loadGoogleIdentityServices() in ./googlePhotos.ts.

/** Browser key for the Maps JavaScript API. Public by design (it is visible in
 *  the script URL), so it must be locked down with an HTTP-referrer
 *  restriction in Google Cloud rather than kept secret. Unset ⇒ the Location
 *  view falls back to a static card instead of an interactive map. */
export const GOOGLE_MAPS_API_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? "";

/** A Map ID is mandatory for Advanced Markers ("if the map ID is missing,
 *  advanced markers cannot load"), so the pins depend on this being set. */
export const GOOGLE_MAPS_MAP_ID = process.env.NEXT_PUBLIC_GOOGLE_MAPS_MAP_ID ?? "";

export const hasGoogleMapsConfig = Boolean(GOOGLE_MAPS_API_KEY && GOOGLE_MAPS_MAP_ID);

const CALLBACK_NAME = "__apartment103InitGoogleMaps";

declare global {
  interface Window {
    [CALLBACK_NAME]?: () => void;
    /** Called by the Maps API itself when the key is rejected. */
    gm_authFailure?: () => void;
  }
}

const authFailureHandlers = new Set<() => void>();

/** A rejected key (wrong key, referrer not allowed, billing disabled) is not a
 *  load error — the script loads fine and then paints Google's own "Oops!
 *  Something went wrong" panel over the map. The only signal is this global
 *  hook, so subscribing to it lets the caller show its own fallback instead.
 *  Returns an unsubscribe function. */
export function onGoogleMapsAuthFailure(handler: () => void): () => void {
  authFailureHandlers.add(handler);
  if (typeof window !== "undefined") {
    window.gm_authFailure = () => {
      for (const h of authFailureHandlers) h();
    };
  }
  return () => {
    authFailureHandlers.delete(handler);
  };
}

let loadPromise: Promise<void> | null = null;

export function loadGoogleMaps(): Promise<void> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Google Maps can only be loaded in the browser."));
  }
  if (!GOOGLE_MAPS_API_KEY) {
    return Promise.reject(new Error("NEXT_PUBLIC_GOOGLE_MAPS_API_KEY is not set."));
  }
  // Guarded on the global `google` namespace rather than `window.google`:
  // googlePhotos.ts augments Window["google"] with the Identity Services
  // shape, which does not carry `maps`.
  if (typeof google !== "undefined" && typeof google.maps?.importLibrary === "function") {
    return Promise.resolve();
  }

  if (!loadPromise) {
    loadPromise = new Promise<void>((resolve, reject) => {
      window[CALLBACK_NAME] = () => resolve();

      const params = new URLSearchParams({
        key: GOOGLE_MAPS_API_KEY,
        // "weekly" is Google's own default channel; pin a quarterly version
        // here if the map ever needs to be held back from an API change.
        v: "weekly",
        // Required for importLibrary() — without it the API loads
        // synchronously and warns about blocking the main thread.
        loading: "async",
        callback: CALLBACK_NAME,
      });

      const script = document.createElement("script");
      script.src = `https://maps.googleapis.com/maps/api/js?${params}`;
      script.async = true;
      script.onerror = () => {
        // Let a later mount retry — a failed load is usually a transient
        // network error rather than a permanently bad key.
        loadPromise = null;
        reject(new Error("Failed to load the Google Maps JavaScript API."));
      };
      document.head.appendChild(script);
    });
  }
  return loadPromise;
}
