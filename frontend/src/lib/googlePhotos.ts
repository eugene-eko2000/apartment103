// Client for the Google Photos Picker API (https://developers.google.com/photos/picker),
// the only sanctioned way for a web app to let a user choose photos from
// their own Google Photos library since Google restricted the old Library
// API's broad `photoslibrary.readonly` scope. There's no official JS SDK for
// it — Google's own docs call it directly over REST with fetch, which is
// what this file does. Authorization comes from Google Identity Services
// (https://accounts.google.com/gsi/client), loaded lazily below.
//
// Flow: get an OAuth access token -> create a picker session -> send the
// admin to session.pickerUri (a Google-hosted page) to choose photos ->
// poll the session until they're done -> list the chosen mediaItems ->
// download each one's bytes with the same access token.

const PICKER_API_BASE = "https://photospicker.googleapis.com/v1";
const PICKER_SCOPE = "https://www.googleapis.com/auth/photospicker.mediaitems.readonly";

interface GoogleTokenResponse {
  access_token: string;
  expires_in: number;
  error?: string;
  error_description?: string;
}

interface GoogleTokenClient {
  requestAccessToken(overrides?: { prompt?: string }): void;
}

declare global {
  interface Window {
    google?: {
      accounts: {
        oauth2: {
          initTokenClient(config: {
            client_id: string;
            scope: string;
            callback: (response: GoogleTokenResponse) => void;
            error_callback?: (error: { type: string; message?: string }) => void;
          }): GoogleTokenClient;
        };
      };
    };
  }
}

let gisLoadPromise: Promise<void> | null = null;

function loadGoogleIdentityServices(): Promise<void> {
  if (typeof window !== "undefined" && window.google?.accounts?.oauth2) return Promise.resolve();
  if (!gisLoadPromise) {
    gisLoadPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Failed to load Google Identity Services."));
      document.head.appendChild(script);
    });
  }
  return gisLoadPromise;
}

let cachedToken: { token: string; expiresAt: number } | null = null;

/**
 * Resolves an OAuth access token scoped to the Photos Picker API, prompting
 * a Google account chooser/consent popup the first time (or once the
 * previous token expires). Must be called from inside a user-gesture event
 * handler (e.g. a button onClick) — browsers block the popup otherwise.
 */
export async function getGooglePhotosAccessToken(): Promise<string> {
  if (cachedToken && cachedToken.expiresAt > Date.now() + 30_000) {
    return cachedToken.token;
  }

  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
  if (!clientId) {
    throw new Error("Google Photos import isn't configured (NEXT_PUBLIC_GOOGLE_CLIENT_ID is unset).");
  }

  await loadGoogleIdentityServices();

  return new Promise((resolve, reject) => {
    const client = window.google!.accounts.oauth2.initTokenClient({
      client_id: clientId,
      scope: PICKER_SCOPE,
      callback: (response) => {
        if (response.error || !response.access_token) {
          reject(new Error(response.error_description || response.error || "Google sign-in was cancelled."));
          return;
        }
        cachedToken = { token: response.access_token, expiresAt: Date.now() + response.expires_in * 1000 };
        resolve(response.access_token);
      },
      error_callback: (error) => {
        reject(new Error(error.message || `Google sign-in failed (${error.type}).`));
      },
    });
    client.requestAccessToken({ prompt: "" });
  });
}

export interface PickerSession {
  id: string;
  pickerUri: string;
  mediaItemsSet: boolean;
  expireTime: string;
  pollingConfig?: { pollInterval?: string; timeoutIn?: string };
}

async function pickerRequest<T>(path: string, accessToken: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${PICKER_API_BASE}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${accessToken}`, ...init.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message || `Google Photos request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function createPickerSession(accessToken: string): Promise<PickerSession> {
  return pickerRequest<PickerSession>("/sessions", accessToken, { method: "POST" });
}

export function getPickerSession(accessToken: string, sessionId: string): Promise<PickerSession> {
  return pickerRequest<PickerSession>(`/sessions/${sessionId}`, accessToken);
}

export function deletePickerSession(accessToken: string, sessionId: string): Promise<void> {
  return pickerRequest<void>(`/sessions/${sessionId}`, accessToken, { method: "DELETE" });
}

// Duration strings from the API look like "5s" (google.protobuf.Duration's
// JSON mapping) — fall back to a sane default for anything else.
export function parsePollIntervalMs(pollInterval: string | undefined, fallbackMs = 2000): number {
  const match = pollInterval ? /^([\d.]+)s$/.exec(pollInterval.trim()) : null;
  if (!match) return fallbackMs;
  return Math.max(1000, Math.round(parseFloat(match[1]) * 1000));
}

export interface PickedMediaItem {
  id: string;
  type?: "PHOTO" | "VIDEO" | "TYPE_UNSPECIFIED";
  mediaFile: {
    baseUrl: string;
    mimeType: string;
    filename: string;
  };
}

export async function listSessionMediaItems(accessToken: string, sessionId: string): Promise<PickedMediaItem[]> {
  const items: PickedMediaItem[] = [];
  let pageToken: string | undefined;
  do {
    const params = new URLSearchParams({ sessionId, pageSize: "100" });
    if (pageToken) params.set("pageToken", pageToken);
    const page = await pickerRequest<{ mediaItems?: PickedMediaItem[]; nextPageToken?: string }>(
      `/mediaItems?${params.toString()}`,
      accessToken
    );
    items.push(...(page.mediaItems ?? []));
    pageToken = page.nextPageToken;
  } while (pageToken);
  return items;
}

// Matches the backend's ALLOWED_CONTENT_TYPES (app/schemas/image.py) —
// anything outside this set (video, other exotic formats) isn't accepted
// for upload. HEIC/HEIF is included: the backend converts it to JPEG.
const SUPPORTED_MIME_TYPES = new Set(["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"]);

export function isSupportedPhoto(item: PickedMediaItem): boolean {
  return item.type !== "VIDEO" && SUPPORTED_MIME_TYPES.has(item.mediaFile.mimeType);
}

export async function downloadMediaItemFile(accessToken: string, item: PickedMediaItem): Promise<File> {
  // "=d" requests the original full-resolution bytes rather than a resized
  // preview — see the Picker API base URL parameters docs. The backend
  // downsizes/recompresses on upload anyway (app/services/image_processing.py).
  const response = await fetch(`${item.mediaFile.baseUrl}=d`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) {
    throw new Error(`Failed to download "${item.mediaFile.filename}" from Google Photos (${response.status})`);
  }
  const blob = await response.blob();
  return new File([blob], item.mediaFile.filename, { type: item.mediaFile.mimeType });
}
