"use client";

import { useEffect, useId, useRef, useState } from "react";
import { FieldChevron, TONE_CLASSES, type FieldTone } from "@/components/field-chrome";

/* A short list picker — preferred language, preferred currency — built the
 * same way as CountrySelect rather than as a native <select>: the two stand
 * side by side in the guest's "Your data" grid, and a native control draws its
 * own arrow, in its own corner, at its own size, which no styling can bring
 * into line with the chevron the combobox beside it hand-draws. Being ours,
 * this one also turns over when the list opens, exactly as that one does.
 *
 * No search box: unlike the ~200 countries, these lists are a handful of
 * entries and there is nothing to filter down to.
 */
export function SelectField({
  label,
  value,
  options,
  noneLabel,
  onChange,
  tone = "booking",
  valid = false,
}: {
  label: string;
  value: string;
  options: string[];
  /** Shown, in placeholder grey, while nothing is chosen; also the first option. */
  noneLabel: string;
  onChange: (v: string) => void;
  tone?: FieldTone;
  valid?: boolean;
}) {
  const id = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLLIElement | null)[]>([]);
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const classes = TONE_CLASSES[tone];

  // The blank choice is an option like any other, so clearing the preference
  // takes the same click as setting one; index 0 keeps it above the rest.
  const items = ["", ...options];

  // Scroll the highlighted option into view whenever the listbox opens (so it
  // lands on the current choice, not the top of the list) or the highlight
  // moves via keyboard.
  useEffect(() => {
    if (!open) return;
    itemRefs.current[highlighted]?.scrollIntoView({ block: "nearest" });
  }, [open, highlighted]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const select = (v: string) => {
    onChange(v);
    setOpen(false);
    buttonRef.current?.focus();
  };

  // Opening always lands the highlight (and, via the scroll effect above, the
  // viewport) on the current choice instead of the top of the list.
  const openList = () => {
    const selectedIndex = items.indexOf(value);
    setHighlighted(selectedIndex === -1 ? 0 : selectedIndex);
    setOpen(true);
  };

  const toggle = () => {
    if (open) {
      setOpen(false);
      return;
    }
    openList();
    buttonRef.current?.focus();
  };

  return (
    <div ref={rootRef} className="relative">
      <label id={`${id}-label`} htmlFor={id} className={`block text-xs font-medium mb-1 ${classes.label}`}>
        {label}
      </label>
      {/* Field and chevron share their own positioning context, so the chevron
          can stretch to the field's height (inset-y-0) rather than naming it —
          the label above stays outside this box. */}
      <div className="relative">
        <button
          ref={buttonRef}
          id={id}
          type="button"
          role="combobox"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={`${id}-listbox`}
          aria-labelledby={`${id}-label ${id}`}
          // mousedown rather than click, for the same reason the chevron uses
          // it: the press must not blur this button, whose onBlur closes the
          // list, or a press while open would close and immediately reopen it.
          onMouseDown={(e) => {
            e.preventDefault();
            toggle();
          }}
          onBlur={() => setOpen(false)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              if (!open) {
                openList();
                return;
              }
              setHighlighted((i) => Math.min(i + 1, items.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setHighlighted((i) => Math.max(i - 1, 0));
            } else if (e.key === "Enter" || e.key === " ") {
              // preventDefault() keeps the browser from turning either key
              // into a click on this button, which would toggle a second time.
              e.preventDefault();
              if (open) select(items[highlighted]);
              else openList();
            } else if (e.key === "Escape") {
              setOpen(false);
            }
          }}
          className={`w-full pl-3 pr-8 py-2 text-sm text-left border focus:outline-none focus:ring-1 cursor-pointer ${
            valid ? classes.validField : classes.field
          }`}
        >
          {/* Placeholder grey lives on a child rather than on the button, so
              it inherits over the field's own text colour instead of racing
              it in the stylesheet. */}
          {value || <span className={classes.empty}>{noneLabel}</span>}
        </button>
        <FieldChevron open={open} tone={tone} />
      </div>
      {open && (
        <ul
          id={`${id}-listbox`}
          role="listbox"
          className={`absolute z-50 mt-1 max-h-56 w-full overflow-auto rounded-lg border shadow-lg py-1 text-sm ${classes.panel}`}
        >
          {items.map((o, i) => (
            <li
              key={o || "none"}
              ref={(el) => {
                itemRefs.current[i] = el;
              }}
              role="option"
              aria-selected={o === value}
              onMouseDown={(e) => {
                e.preventDefault();
                select(o);
              }}
              onMouseEnter={() => setHighlighted(i)}
              className={`px-3 py-1.5 cursor-pointer ${i === highlighted ? classes.highlighted : classes.item} ${
                o ? "" : classes.empty
              }`}
            >
              {o || noneLabel}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
