/* The header nav links' look, shared so that the three view-opening items
 * (gallery, amenities, location) cannot drift apart — they are rendered by
 * three separate components but read as one row. */
export const NAV_LINK_CLASS =
  "text-left hover:text-teal-700 dark:hover:text-teal-400 transition-colors cursor-pointer";

/** Added to the nav item whose view is currently open, where pressing it
 *  closes that view again. */
export const NAV_ACTIVE_CLASS = "text-teal-700 dark:text-teal-400 font-medium";
