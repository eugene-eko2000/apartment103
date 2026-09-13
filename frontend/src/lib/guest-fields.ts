/* Character rules for the free-text fields of the guest "Your data" form.
 *
 * Two separate jobs live here, and they are deliberately not the same rule:
 *
 *  - `sanitize*` runs on every keystroke and strips what cannot belong in the
 *    field at all — a digit in a first name, an "@" in a city. The guest never
 *    gets to commit the typo, so there is nothing to explain to them after the
 *    fact (which also keeps this out of the four dictionaries).
 *  - `isValid*` answers whether what survived is a usable value, which is
 *    weaker than "matches this country's format": these records are filled in
 *    by guests from anywhere, so anything beyond "a few characters, of the
 *    right kind, in a plausible order" would reject real addresses.
 */

// Whitespace of any kind collapses to one plain space before the per-field
// filter runs. Dropping it instead (it is outside every allowed set below)
// would glue words together when a value is pasted out of an address book:
// "123 Main\nSt" -> "123 MainSt".
const WHITESPACE = /\s+/g;

// A doubled separator ("Jo--hn", "Main  St") is always a slip, never a
// spelling — collapse the run to the single character that was meant.
const REPEATED_SEPARATOR = /([ '’.,\-/#])\1+/gu;

type FieldRule = {
  /** Everything the field may *not* contain, stripped as the guest types. */
  forbidden: RegExp;
  /** What may not open the value — a name never starts with "-" or a space. */
  leading: RegExp;
  maxLength: number;
};

// Letters (any alphabet) and the combining marks that go with them, plus the
// three separators that genuinely occur inside personal and place names:
// "Anne-Marie", "O’Brien", "St. Gallen". No digits, no other punctuation.
const NAME_RULE: FieldRule = {
  forbidden: /[^\p{L}\p{M}'’ .-]/gu,
  leading: /^[^\p{L}]+/u,
  maxLength: 60,
};

// Same alphabet as a name; only the cap differs ("Llanfairpwllgwyngyll…").
const PLACE_RULE: FieldRule = { ...NAME_RULE, maxLength: 85 };

// A street line is the one field that needs digits, and the one where "/"
// (3/a), "," and "#" carry meaning.
const STREET_RULE: FieldRule = {
  forbidden: /[^\p{L}\p{M}\p{N}'’ ,.\-/#°º]/gu,
  leading: /^[^\p{L}\p{N}]+/u,
  maxLength: 120,
};

// Postal codes worldwide are letters, digits, and the space or hyphen that
// groups them: "75001", "EC1A 1BB", "K1A 0B1", "962-0011".
const ZIP_RULE: FieldRule = {
  forbidden: /[^\p{L}\p{N} -]/gu,
  leading: /^[^\p{L}\p{N}]+/u,
  maxLength: 12,
};

function sanitize(value: string, rule: FieldRule): string {
  return value
    .replace(WHITESPACE, " ")
    .replace(rule.forbidden, "")
    .replace(REPEATED_SEPARATOR, "$1")
    .replace(rule.leading, "")
    .slice(0, rule.maxLength);
}

export const sanitizeName = (value: string) => sanitize(value, NAME_RULE);
export const sanitizePlace = (value: string) => sanitize(value, PLACE_RULE);
export const sanitizeStreet = (value: string) => sanitize(value, STREET_RULE);
export const sanitizeZip = (value: string) => sanitize(value, ZIP_RULE);

const letterCount = (value: string) => (value.match(/\p{L}/gu) ?? []).length;

// Two letters is the shortest real name there is ("Ng", "Bo"), and a name
// that trails off in a hyphen or an apostrophe is a half-typed one — a
// trailing "." is not, because initials end that way ("Jr.").
export function isValidName(value: string): boolean {
  const v = value.trim();
  return letterCount(v) >= 2 && /^\p{L}/u.test(v) && /[\p{L}\p{M}.]$/u.test(v);
}

/** City, and the optional state/region line, read the same way as a name. */
export const isValidPlace = isValidName;

export function isValidStreet(value: string): boolean {
  const v = value.trim();
  // A house number is not universal (named houses, rural addresses), so the
  // only thing required beyond a plausible length is an actual word.
  return v.length >= 3 && letterCount(v) >= 2 && /^[\p{L}\p{N}]/u.test(v);
}

export function isValidZip(value: string): boolean {
  const v = value.trim();
  // Formats differ per country, so the rule that holds everywhere is: a few
  // characters, at least one of them a digit.
  return v.length >= 3 && v.length <= 12 && /\p{N}/u.test(v);
}

/** The state/region field is optional — blank is acceptable, half-typed isn't. */
export function isValidOptionalPlace(value: string): boolean {
  return value.trim() === "" || isValidPlace(value);
}
