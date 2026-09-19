"use client";

import { useEffect } from "react";
import { getGuest } from "@/lib/api";
import { onGuestSessionChange, readGuestSession } from "@/lib/guest-auth";
import { clearSessionPreferences } from "@/lib/session-preferences";
import { useApplyGuestPreferences } from "@/lib/guest-preferences";

// Mounted once near the root (see [lang]/layout.tsx). Makes a logged-in
// guest's saved preferred_language/preferred_currency the site's active
// locale/currency: on first load (an existing session from a previous
// visit) and again every time the session changes (login via the header or
// the booking flow). Renders nothing — this is a pure side-effect.
export default function GuestPreferenceSync() {
  const applyGuestPreferences = useApplyGuestPreferences();

  useEffect(() => {
    const sync = () => {
      const session = readGuestSession();
      if (!session) {
        // Signed out: the PREFERRED_CURRENCY / NEXT_LOCALE cookies are
        // authoritative again, so a pick left over from the session that
        // just ended must not keep shadowing them.
        clearSessionPreferences();
        return;
      }
      if (!session.guestId) return;
      getGuest(session.guestId, session.token).then(applyGuestPreferences).catch(() => {});
    };
    // Deferred to a microtask so the localStorage read (and any resulting
    // navigation/context update) isn't synchronous within the effect body.
    queueMicrotask(sync);
    return onGuestSessionChange(sync);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}
