const STORAGE_KEY = "guest_session";
const SESSION_EVENT = "guest-session-change";

export interface GuestSession {
  token: string;
  // null until the guest profile itself is created (self-registration / admin booking)
  guestId: string | null;
  guestMode: "create" | "update";
  isAdminBooking: boolean;
  expiresAt: number;
}

export function readGuestSession(): GuestSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as GuestSession;
    if (!parsed.token || !parsed.guestMode || !parsed.expiresAt || parsed.expiresAt <= Date.now()) {
      window.localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return parsed;
  } catch {
    window.localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function saveGuestSession(session: GuestSession): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  window.dispatchEvent(new Event(SESSION_EVENT));
}

// Called when the API rejects a bearer token. If it is the one we have
// stored, the session is over — most often because it simply expired, but
// also when the guest's data was wiped by the backend's retention sweep and
// their record stopped being an account. Either way the stored session is
// dead, and keeping it would leave the UI showing a signed-in header over an
// account that answers 401 to everything.
//
// Token-matched rather than unconditional: an admin call getting a 401 must
// not sign a guest out of the same browser.
export function clearGuestSessionIfToken(token: string): void {
  if (typeof window === "undefined") return;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return;
  try {
    if ((JSON.parse(raw) as GuestSession).token === token) clearGuestSession();
  } catch {
    clearGuestSession();
  }
}

export function clearGuestSession(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  window.dispatchEvent(new Event(SESSION_EVENT));
}

// Notifies other components in the same tab (via the custom event dispatched
// above) or other tabs (via the native "storage" event) when the guest
// session changes, so e.g. the header's login state stays in sync with the
// booking widget's. Returns an unsubscribe function.
export function onGuestSessionChange(callback: () => void): () => void {
  window.addEventListener(SESSION_EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(SESSION_EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}
