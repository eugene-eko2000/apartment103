"use client";

import { useEffect } from "react";

export function Modal({
  title,
  onClose,
  children,
  footer,
  maxHeight = "90vh",
  maxWidth = "max-w-lg",
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  /** Fixed action bar rendered below the scrollable content, outside the scroll area. */
  footer?: React.ReactNode;
  /** CSS max-height for the dialog box, e.g. "calc(100vh - 120px)". */
  maxHeight?: string;
  /** Tailwind max-width class for the dialog box, e.g. "max-w-2xl". */
  maxWidth?: string;
}) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={`bg-white dark:bg-slate-800 rounded-xl shadow-2xl w-full ${maxWidth} flex flex-col overflow-hidden`} style={{ maxHeight }}>
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between shrink-0 bg-white dark:bg-slate-800 rounded-t-xl">
          <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 text-xl leading-none cursor-pointer"
          >
            ×
          </button>
        </div>
        <div className="p-6 overflow-y-auto">{children}</div>
        {footer && (
          <div className="px-6 py-4 border-t border-slate-200 dark:border-slate-700 shrink-0">{footer}</div>
        )}
      </div>
    </div>
  );
}
