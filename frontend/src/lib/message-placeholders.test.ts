import { describe, expect, it } from "vitest";
import {
  completionRange,
  describeSchedule,
  findPlaceholderTrigger,
  imageReferences,
  imageToken,
  matchPlaceholders,
  removeImageReferences,
  spliceText,
  substitutePlaceholders,
  unknownPlaceholders,
} from "./message-placeholders";

describe("findPlaceholderTrigger", () => {
  it("opens right after a typed {{", () => {
    expect(findPlaceholderTrigger("Hello {{", 8)).toEqual({ start: 6, query: "" });
  });

  it("tracks the partial name typed after the braces", () => {
    expect(findPlaceholderTrigger("Hello {{gue", 11)).toEqual({ start: 6, query: "gue" });
    expect(findPlaceholderTrigger("Hello {{ gue", 12)).toEqual({ start: 6, query: "gue" });
  });

  it("only looks at the text before the caret", () => {
    expect(findPlaceholderTrigger("Hello {{gue and more", 11)).toEqual({ start: 6, query: "gue" });
  });

  it("closes once the token is finished or abandoned", () => {
    expect(findPlaceholderTrigger("Hello {{guest_first_name}}", 26)).toBeNull();
    expect(findPlaceholderTrigger("Hello {{gue st", 14)).toBeNull();
    expect(findPlaceholderTrigger("Hello {", 7)).toBeNull();
  });
});

describe("matchPlaceholders", () => {
  it("lists every placeholder for an empty query", () => {
    expect(matchPlaceholders("")).toHaveLength(8);
  });

  it("puts prefix matches before substring matches", () => {
    expect(matchPlaceholders("check").map((p) => p.name)).toEqual(["checkin_date", "checkout_date"]);
    expect(matchPlaceholders("date").map((p) => p.name)).toEqual(["checkin_date", "checkout_date"]);
    expect(matchPlaceholders("children")[0].name).toBe("children_older_6yo_number");
  });

  it("is empty when nothing matches", () => {
    expect(matchPlaceholders("zzz")).toEqual([]);
  });
});

describe("completionRange", () => {
  it("replaces from the braces to the caret", () => {
    const text = "Hi {{gu there";
    expect(completionRange(text, { start: 3, query: "gu" }, 7)).toEqual([3, 7]);
  });

  it("swallows closing braces already after the caret", () => {
    const text = "Hi {{gu}} there";
    const [start, end] = completionRange(text, { start: 3, query: "gu" }, 7);
    expect(spliceText(text, start, end, "{{guest_first_name}}")).toBe("Hi {{guest_first_name}} there");
  });
});

describe("substitutePlaceholders", () => {
  it("fills known names, tolerating spaces, and leaves unknown ones alone", () => {
    expect(
      substitutePlaceholders("Hi {{guest_first_name}}, {{ stay_days }} nights {{nope}}", {
        guest_first_name: "Anna",
        stay_days: "4",
      })
    ).toBe("Hi Anna, 4 nights {{nope}}");
  });
});

describe("unknownPlaceholders", () => {
  it("names each unknown placeholder once", () => {
    expect(unknownPlaceholders("{{guest_firstname}} {{checkin_date}} {{guest_firstname}}")).toEqual([
      "guest_firstname",
    ]);
  });
});

const IMG = "6abecb03f4a916f6bcaf1064";
const OTHER = "6abecb03f4a916f6bcaf1065";

describe("image placeholders", () => {
  it("have a token per image id", () => {
    expect(imageToken(IMG)).toBe(`{{image:${IMG}}}`);
  });

  it("are listed once each, in order", () => {
    expect(imageReferences(`a {{image:${OTHER}}} b {{image:${IMG}}} {{image:${OTHER}}}`)).toEqual([OTHER, IMG]);
  });

  it("are known placeholders", () => {
    expect(unknownPlaceholders(`{{image:${IMG}}} {{image:nope}}`)).toEqual(["image:nope"]);
  });

  it("render through the given markdown and vanish when unknown", () => {
    const text = `A {{image:${IMG}}} B {{image:${OTHER}}} {{guest_first_name}}`;
    expect(substitutePlaceholders(text, { guest_first_name: "Anna" }, { [IMG]: "![](x.png)" })).toBe(
      "A ![](x.png) B  Anna"
    );
    expect(substitutePlaceholders(text, {})).toBe(`A {{image:${IMG}}} B {{image:${OTHER}}} `);
  });

  it("can be stripped for one image", () => {
    expect(removeImageReferences(`A{{image:${IMG}}}B{{image:${OTHER}}}`, IMG)).toBe(`AB{{image:${OTHER}}}`);
  });
});

describe("describeSchedule", () => {
  it("reads as a sentence", () => {
    expect(describeSchedule({ anchor: "booking_date", direction: "after", offset_days: 1 })).toBe(
      "1 day after booking"
    );
    expect(describeSchedule({ anchor: "checkin", direction: "before", offset_days: 2 })).toBe(
      "2 days before check-in"
    );
    expect(describeSchedule({ anchor: "checkout", direction: "before", offset_days: 0 })).toBe(
      "On the check-out day"
    );
  });
});
