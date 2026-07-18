"use client";

import { useEffect, useRef, useState } from "react";

export function RepeatingRows<T>({
  label,
  items,
  onChange,
  renderRow,
  emptyRow,
  addLabel = "Add row",
  maxHeight,
}: {
  label: string;
  items: T[];
  onChange: (items: T[]) => void;
  renderRow: (item: T, update: (patch: Partial<T>) => void, index: number, isNew: boolean) => React.ReactNode;
  emptyRow: () => T;
  addLabel?: string;
  /** Caps the row list's height (e.g. "16rem"), scrolling internally past that instead of growing the form. */
  maxHeight?: string;
}) {
  const [newlyAddedIndex, setNewlyAddedIndex] = useState<number | null>(null);
  const rowRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  const updateAt = (index: number, patch: Partial<T>) => {
    onChange(items.map((it, i) => (i === index ? { ...it, ...patch } : it)));
  };
  const removeAt = (index: number) => {
    onChange(items.filter((_, i) => i !== index));
  };

  // Scroll the freshly added row into view once its DOM node exists, then
  // clear the flag so a later index shift (e.g. removing an earlier row)
  // can't make a stale index look "new" again.
  useEffect(() => {
    if (newlyAddedIndex === null) return;
    rowRefs.current.get(newlyAddedIndex)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setNewlyAddedIndex(null);
  }, [newlyAddedIndex]);

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="block text-xs font-medium text-slate-500 dark:text-slate-400">{label}</span>
        <button
          type="button"
          onClick={() => {
            setNewlyAddedIndex(items.length);
            onChange([...items, emptyRow()]);
          }}
          className="text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 cursor-pointer"
        >
          + {addLabel}
        </button>
      </div>
      {items.length === 0 && <p className="text-xs text-slate-400 dark:text-slate-500 italic mb-2">None yet.</p>}
      <div className={`space-y-2 ${maxHeight ? "overflow-y-auto pr-1" : ""}`} style={maxHeight ? { maxHeight } : undefined}>
        {items.map((item, index) => (
          <div
            key={index}
            ref={(el) => {
              if (el) rowRefs.current.set(index, el);
              else rowRefs.current.delete(index);
            }}
            className="flex items-end gap-2 bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg p-2"
          >
            <div className="flex-1 grid grid-cols-2 sm:grid-cols-3 gap-2">
              {renderRow(item, (patch) => updateAt(index, patch), index, index === newlyAddedIndex)}
            </div>
            <button
              type="button"
              onClick={() => removeAt(index)}
              aria-label="Remove row"
              className="text-slate-400 dark:text-slate-500 hover:text-red-600 dark:hover:text-red-400 text-lg leading-none px-1 pb-1.5 cursor-pointer"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
