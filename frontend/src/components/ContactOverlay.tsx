"use client";

import { useEffect } from "react";
import { createPortal } from "react-dom";
import SiteHeader from "./SiteHeader";
import SiteFooter from "./SiteFooter";
import type { Dictionary } from "@/app/[lang]/dictionaries";
import type { Locale } from "@/lib/i18n-config";

/* Names and addresses are not translated — only the country line is, and
 * that comes from the dictionary. */
const CONTACT_NAME = "Berg See Home Apartment";
const CONTACT_STREET = "Gostenstrasse 26";
const CONTACT_CITY = "8002 Unterterzen";
const CONTACT_EMAIL = "info@bergseehome.ch";

export default function ContactOverlay({
  lang,
  dict,
  onClose,
}: {
  lang: Locale;
  dict: Dictionary;
  onClose: () => void;
}) {
  const c = dict.contact;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return createPortal(
    <div className="fixed inset-0 z-50 flex flex-col bg-gray-50/75 dark:bg-gray-950/80 backdrop-blur-md">
      {/* Same as the amenities and location views: the header's "Contact" slot
          closes this layer, and its other slots replace it rather than stack. */}
      <SiteHeader lang={lang} dict={dict} />

      <div className="relative flex-1 min-h-0">
        <button
          onClick={onClose}
          aria-label={c.backHome}
          className="absolute top-5 right-6 sm:top-8 sm:right-12 z-10 text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-200 transition-colors text-3xl sm:text-5xl leading-none cursor-pointer"
        >
          ✕
        </button>

        <div className="h-full overflow-y-auto">
          <div className="max-w-5xl mx-auto px-6 py-10">
            <h1 className="text-3xl lg:text-4xl font-bold text-gray-900 dark:text-gray-100 mb-2">{c.pageTitle}</h1>
            <p className="text-gray-500 dark:text-gray-400 mb-6">{c.subtitle}</p>

            <div className="max-w-xl bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-5 sm:p-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-5">{CONTACT_NAME}</h2>

              <dl className="space-y-4 text-sm">
                <div className="flex gap-3">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="shrink-0 mt-0.5 text-teal-600 dark:text-teal-400">
                    <path
                      d="M12 21s-7-7.5-7-12a7 7 0 0 1 14 0c0 4.5-7 12-7 12Z"
                      stroke="currentColor"
                      strokeWidth="1.75"
                      strokeLinejoin="round"
                    />
                    <circle cx="12" cy="9" r="2.5" stroke="currentColor" strokeWidth="1.75" />
                  </svg>
                  <div>
                    <dt className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">{c.addressLabel}</dt>
                    <dd className="text-gray-900 dark:text-gray-100">
                      <address className="not-italic leading-relaxed">
                        {CONTACT_STREET}
                        <br />
                        {CONTACT_CITY}, {c.country}
                      </address>
                    </dd>
                  </div>
                </div>

                <div className="flex gap-3">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="shrink-0 mt-0.5 text-teal-600 dark:text-teal-400">
                    <rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="1.75" />
                    <path d="m3.5 6.5 8.5 6.5 8.5-6.5" stroke="currentColor" strokeWidth="1.75" strokeLinejoin="round" />
                  </svg>
                  <div>
                    <dt className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">{c.emailLabel}</dt>
                    <dd>
                      <a
                        href={`mailto:${CONTACT_EMAIL}`}
                        className="text-teal-700 dark:text-teal-400 hover:underline break-all"
                      >
                        {CONTACT_EMAIL}
                      </a>
                    </dd>
                  </div>
                </div>
              </dl>
            </div>
          </div>
        </div>
      </div>

      <SiteFooter dict={dict} />
    </div>,
    document.body
  );
}
