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
