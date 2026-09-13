/* The two palettes the guest-facing and admin-facing form fields are drawn
 * in. Shared rather than per-component so that fields standing side by side —
 * CountrySelect and SelectField in the same "Your data" grid — cannot drift
 * apart in border radius, chevron colour, or the green that marks a filled
 * field.
 */
export const TONE_CLASSES = {
  booking: {
    label: "text-gray-500 dark:text-gray-400",
    field:
      "rounded-xl border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 focus:ring-teal-300 focus:border-teal-400",
    // Same field, once a real value is picked: the neutral border is
    // replaced (never merely overridden) by the shared valid-field green.
    validField:
      "rounded-xl border-emerald-400 dark:border-emerald-500 field-valid bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 focus:ring-teal-300 focus:border-teal-400",
    panel: "border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800",
    item: "hover:bg-gray-50 dark:hover:bg-gray-700",
    highlighted: "bg-gray-50 dark:bg-gray-700",
    empty: "text-gray-400 dark:text-gray-500",
    chevron: "text-gray-600 dark:text-gray-300",
  },
  admin: {
    label: "text-slate-500 dark:text-slate-400",
    field:
      "rounded-lg border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 focus:ring-indigo-400 focus:border-indigo-500",
    validField:
      "rounded-lg border-emerald-400 dark:border-emerald-500 field-valid bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 focus:ring-indigo-400 focus:border-indigo-500",
    panel: "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-700",
    item: "hover:bg-slate-100 dark:hover:bg-slate-600",
    highlighted: "bg-slate-100 dark:bg-slate-600",
    empty: "text-slate-400 dark:text-slate-500",
    chevron: "text-slate-600 dark:text-slate-300",
  },
} as const;

export type FieldTone = keyof typeof TONE_CLASSES;

/* The affordance a native <select> draws for itself, which the two hand-built
 * pickers here — a combobox <input> and a listbox <button> — have to draw for
 * themselves. One component, so both wear the same glyph in the same corner
 * and turn over at the same moment.
 *
 * It fills the right edge of whatever `relative` box holds the field,
 * stretching to that field's height (inset-y-0) rather than naming it.
 *
 * `onToggle` says who handles the press. A field that is itself clickable (a
 * listbox <button>) leaves it out, and the glyph lets the press through to the
 * field beneath. A field that is not (a text <input>, where a click only ever
 * opens) passes it, and the glyph becomes the button that also closes.
 */
export function FieldChevron({
  open,
  tone = "booking",
  onToggle,
}: {
  open: boolean;
  tone?: FieldTone;
  onToggle?: () => void;
}) {
  const position = `absolute inset-y-0 right-0 flex w-6 items-center justify-center ${TONE_CLASSES[tone].chevron}`;
  const glyph = (
    <svg
      viewBox="0 0 16 16"
      className={`h-3.5 w-3.5 transition-transform duration-150 ${open ? "rotate-180" : ""}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m4 6 4 4 4-4" />
    </svg>
  );

  // Out of the tab order and hidden from assistive tech either way: the field
  // beside it is the combobox and already says aria-expanded.
  if (!onToggle) {
    return (
      <span aria-hidden="true" className={`pointer-events-none ${position}`}>
        {glyph}
      </span>
    );
  }
  return (
    <button
      type="button"
      tabIndex={-1}
      aria-hidden="true"
      // mousedown rather than click, and preventDefault()ed: the press must
      // not blur the field, whose onBlur closes the list — a click while open
      // would otherwise close and immediately reopen it.
      onMouseDown={(e) => {
        e.preventDefault();
        onToggle();
      }}
      className={`${position} cursor-pointer`}
    >
      {glyph}
    </button>
  );
}
