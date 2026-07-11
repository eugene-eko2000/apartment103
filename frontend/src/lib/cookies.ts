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
