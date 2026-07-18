"use client";

import { useCookieConsent } from "@/lib/cookie-consent-context";

export default function CookieConsentBanner({
  dict,
}: {
  dict: { message: string; allow: string; deny: string };
}) {
  const { status, allow, deny } = useCookieConsent();

  if (status !== "pending") return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-[100] p-4 sm:p-6">
      <div className="max-w-3xl mx-auto bg-white dark:bg-gray-800 rounded-2xl shadow-lg border border-gray-100 dark:border-gray-700 p-4 sm:p-5 flex flex-col sm:flex-row items-center gap-4">
        <p className="text-sm text-gray-600 dark:text-gray-300 flex-1 text-center sm:text-left">
          {dict.message}
        </p>
        <div className="flex items-center gap-3 shrink-0">
          <button
            type="button"
            onClick={deny}
            className="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 transition-colors cursor-pointer"
          >
            {dict.deny}
          </button>
          <button
            type="button"
            onClick={allow}
            className="px-4 py-2 text-sm font-medium text-white rounded-lg cursor-pointer transition-opacity hover:opacity-90"
            style={{ background: "linear-gradient(135deg, #0f766e, #0891b2)" }}
          >
            {dict.allow}
          </button>
        </div>
      </div>
    </div>
  );
}
