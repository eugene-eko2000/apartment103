// The anonymous language / currency settings. Authoritative for a signed-out
// visitor, and for a signed-in guest whose profile leaves the matching field
// at "No Preference" (see session-preferences).
export const LOCALE_COOKIE = "NEXT_LOCALE";
export const CURRENCY_COOKIE = "PREFERRED_CURRENCY";

// How long a remembered setting lives, in days.
export const PREFERENCE_COOKIE_DAYS = 365;

export function getCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`));
  return match?.split("=")[1];
}

export function setCookie(name: string, value: string, maxAgeDays: number) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=${value};path=/;max-age=${maxAgeDays * 24 * 60 * 60}`;
}
