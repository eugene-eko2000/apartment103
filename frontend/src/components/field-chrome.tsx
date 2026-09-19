/* The two palettes the guest-facing and admin-facing form fields are drawn
 * in. Shared rather than per-component so that fields standing side by side —
 * CountrySelect and SelectField in the same "Your data" grid — cannot drift
 * apart in border radius or the green that marks a filled field.
 *
 * The ink is kept out of `field`/`validField` and named separately: a field
 * showing its placeholder swaps `text` for `empty`, and two text-colour
 * utilities on one element would otherwise be decided by stylesheet order
 * rather than by which one the component asked for.
 */
export const TONE_CLASSES = {
  booking: {
    label: "text-gray-500 dark:text-gray-400",
    field:
      "rounded-xl border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 focus:ring-teal-300 focus:border-teal-400",
    // Same field, once a real value is picked: the neutral border is
    // replaced (never merely overridden) by the shared valid-field green.
    validField:
      "rounded-xl border-emerald-400 dark:border-emerald-500 field-valid bg-white dark:bg-gray-800 focus:ring-teal-300 focus:border-teal-400",
    text: "text-gray-800 dark:text-gray-100",
    empty: "text-gray-400 dark:text-gray-500",
  },
  admin: {
    label: "text-slate-500 dark:text-slate-400",
    field:
      "rounded-lg border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 focus:ring-indigo-400 focus:border-indigo-500",
    validField:
      "rounded-lg border-emerald-400 dark:border-emerald-500 field-valid bg-white dark:bg-slate-700 focus:ring-indigo-400 focus:border-indigo-500",
    text: "text-slate-800 dark:text-slate-100",
    empty: "text-slate-400 dark:text-slate-500",
  },
} as const;

export type FieldTone = keyof typeof TONE_CLASSES;
