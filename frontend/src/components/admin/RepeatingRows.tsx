"use client";

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
  renderRow: (item: T, update: (patch: Partial<T>) => void, index: number) => React.ReactNode;
  emptyRow: () => T;
  addLabel?: string;
  /** Caps the row list's height (e.g. "16rem"), scrolling internally past that instead of growing the form. */
  maxHeight?: string;
}) {
  const updateAt = (index: number, patch: Partial<T>) => {
    onChange(items.map((it, i) => (i === index ? { ...it, ...patch } : it)));
  };
  const removeAt = (index: number) => {
    onChange(items.filter((_, i) => i !== index));
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="block text-xs font-medium text-slate-500">{label}</span>
        <button
          type="button"
          onClick={() => onChange([...items, emptyRow()])}
          className="text-xs font-medium text-indigo-600 hover:text-indigo-800 cursor-pointer"
        >
          + {addLabel}
        </button>
      </div>
      {items.length === 0 && <p className="text-xs text-slate-400 italic mb-2">None yet.</p>}
      <div className={`space-y-2 ${maxHeight ? "overflow-y-auto pr-1" : ""}`} style={maxHeight ? { maxHeight } : undefined}>
        {items.map((item, index) => (
          <div key={index} className="flex items-end gap-2 bg-slate-50 border border-slate-200 rounded-lg p-2">
            <div className="flex-1 grid grid-cols-2 sm:grid-cols-3 gap-2">
              {renderRow(item, (patch) => updateAt(index, patch), index)}
            </div>
            <button
              type="button"
              onClick={() => removeAt(index)}
              aria-label="Remove row"
              className="text-slate-400 hover:text-red-600 text-lg leading-none px-1 pb-1.5 cursor-pointer"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
