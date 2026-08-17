"use client";

import { useEffect } from "react";
import { createPortal } from "react-dom";

export interface PrivacyModalDict {
  title: string;
  close: string;
  intro: string;
  sections: { heading: string; body: string }[];
}

export default function PrivacyModal({ dict, onClose }: { dict: PrivacyModalDict; onClose: () => void }) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden">
        <div
          className="px-6 py-4 rounded-t-2xl flex items-center justify-between shrink-0"
          style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
        >
          <h2 className="text-lg font-bold text-white">{dict.title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={dict.close}
            className="text-white/80 hover:text-white text-xl leading-none cursor-pointer"
          >
            ×
          </button>
        </div>

        <div className="p-6 space-y-5 text-sm text-gray-600 dark:text-gray-300 overflow-y-auto">
          <p>{dict.intro}</p>
          {dict.sections.map((section) => (
            <div key={section.heading}>
              <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-1">{section.heading}</h3>
              <p>{section.body}</p>
            </div>
          ))}
        </div>
      </div>
    </div>,
    document.body
  );
}
