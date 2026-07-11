"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { getCookie, setCookie } from "./cookies";

export const CONSENT_COOKIE = "COOKIE_CONSENT";
export type ConsentStatus = "pending" | "allowed" | "denied";

const CookieConsentContext = createContext<{
  status: ConsentStatus;
  allow: () => void;
  deny: () => void;
}>({
  status: "pending",
  allow: () => {},
  deny: () => {},
});

export function CookieConsentProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<ConsentStatus>("pending");

  useEffect(() => {
    const stored = getCookie(CONSENT_COOKIE);
    if (stored === "allowed" || stored === "denied") {
      setStatus(stored);
    }
  }, []);

  const allow = () => {
    setStatus("allowed");
    setCookie(CONSENT_COOKIE, "allowed", 365);
  };

  const deny = () => {
    setStatus("denied");
    setCookie(CONSENT_COOKIE, "denied", 365);
  };

  return (
    <CookieConsentContext.Provider value={{ status, allow, deny }}>
      {children}
    </CookieConsentContext.Provider>
  );
}

export function useCookieConsent() {
  return useContext(CookieConsentContext);
}
