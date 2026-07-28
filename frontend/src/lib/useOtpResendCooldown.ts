"use client";

import { useEffect, useState } from "react";

// Tracks when the "Resend code" action becomes available again. The backend
// silently no-ops OTP requests made within its cooldown window (to keep the
// request idempotent for retries), so the client must independently disable
// resend and count down using the retry_after_seconds it returns.
export function useOtpResendCooldown() {
  const [availableAt, setAvailableAt] = useState<number | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(0);

  useEffect(() => {
    if (availableAt === null) return;
    const tick = () => setSecondsLeft(Math.max(0, Math.ceil((availableAt - Date.now()) / 1000)));
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [availableAt]);

  return {
    secondsLeft,
    start: (retryAfterSeconds: number) => setAvailableAt(Date.now() + retryAfterSeconds * 1000),
    reset: () => setAvailableAt(null),
  };
}
