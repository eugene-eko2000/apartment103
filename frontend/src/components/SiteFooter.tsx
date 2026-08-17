"use client";

import { useState } from "react";
import type { Dictionary } from "@/app/[lang]/dictionaries";
import PrivacyModal from "./PrivacyModal";

export default function SiteFooter({ dict }: { dict: Dictionary }) {
  const [showPrivacy, setShowPrivacy] = useState(false);

  return (
    <footer id="site-footer" className="shrink-0 border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
      <div className="max-w-7xl mx-auto px-6 py-3 flex flex-col sm:flex-row items-center justify-between gap-2 text-sm text-gray-400 dark:text-gray-500">
        <span>{dict.footer.copyright.replace("{year}", String(new Date().getFullYear()))}</span>
        <div className="flex gap-6">
          <button
            type="button"
            onClick={() => setShowPrivacy(true)}
            className="hover:text-teal-700 dark:hover:text-teal-400 transition-colors cursor-pointer"
          >
            {dict.footer.privacy}
          </button>
          <a href="#" className="hover:text-teal-700 dark:hover:text-teal-400 transition-colors">{dict.footer.terms}</a>
          <a href="#" className="hover:text-teal-700 dark:hover:text-teal-400 transition-colors">{dict.footer.contact}</a>
        </div>
      </div>
      {showPrivacy && <PrivacyModal dict={dict.footer.privacyModal} onClose={() => setShowPrivacy(false)} />}
    </footer>
  );
}
