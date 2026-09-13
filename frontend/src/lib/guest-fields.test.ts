import { describe, expect, it } from "vitest";
import {
  isValidName,
  isValidOptionalPlace,
  isValidPlace,
  isValidStreet,
  isValidZip,
  sanitizeName,
  sanitizePlace,
  sanitizeStreet,
  sanitizeZip,
} from "./guest-fields";

describe("sanitizeName", () => {
  it("keeps letters from any alphabet and name punctuation", () => {
    expect(sanitizeName("Anne-Marie")).toBe("Anne-Marie");
    expect(sanitizeName("O’Brien")).toBe("O’Brien");
    expect(sanitizeName("Müller")).toBe("Müller");
    expect(sanitizeName("Ковалёв")).toBe("Ковалёв");
    expect(sanitizeName("Le Van Thanh")).toBe("Le Van Thanh");
  });

  it("drops digits and symbols that cannot occur in a name", () => {
    expect(sanitizeName("John3")).toBe("John");
    expect(sanitizeName("<script>")).toBe("script");
    expect(sanitizeName("a@b.com")).toBe("ab.com");
  });

  it("normalises whitespace, repeats and a punctuation opener", () => {
    expect(sanitizeName("Jo  hn")).toBe("Jo hn");
    expect(sanitizeName("Jo--hn")).toBe("Jo-hn");
    expect(sanitizeName("  John")).toBe("John");
    expect(sanitizeName("-John")).toBe("John");
    expect(sanitizeName("Mary\nAnn")).toBe("Mary Ann");
  });

  it("caps the length", () => {
    expect(sanitizeName("a".repeat(200))).toHaveLength(60);
  });
});

describe("isValidName / isValidPlace", () => {
  it("accepts real names", () => {
    for (const n of ["Ng", "John", "Anne-Marie", "O’Brien", "Ковалёв", "Jr."]) {
      expect(isValidName(n)).toBe(true);
    }
  });

  it("rejects half-typed values", () => {
    for (const n of ["", " ", "J", "J-", "O’"]) {
      expect(isValidName(n)).toBe(false);
    }
  });

  it("treats a city the same way", () => {
    expect(isValidPlace("St. Gallen")).toBe(true);
    expect(isValidPlace("L")).toBe(false);
  });

  it("accepts a blank state line but not a broken one", () => {
    expect(isValidOptionalPlace("")).toBe(true);
    expect(isValidOptionalPlace("   ")).toBe(true);
    expect(isValidOptionalPlace("Ticino")).toBe(true);
    expect(isValidOptionalPlace("T-")).toBe(false);
  });
});

describe("street address", () => {
  it("keeps digits and address punctuation", () => {
    expect(sanitizeStreet("Via Roma 3/a")).toBe("Via Roma 3/a");
    expect(sanitizeStreet("1600 Pennsylvania Ave, NW")).toBe("1600 Pennsylvania Ave, NW");
    expect(sanitizeStreet("Apt #4")).toBe("Apt #4");
  });

  it("drops symbols and a punctuation opener", () => {
    expect(sanitizeStreet("Main St <b>")).toBe("Main St b");
    expect(sanitizeStreet("/ Main St")).toBe("Main St");
  });

  it("requires a word, not just a number", () => {
    expect(isValidStreet("Via Roma 3")).toBe(true);
    expect(isValidStreet("12")).toBe(false);
    expect(isValidStreet("ab")).toBe(false);
  });
});

describe("postal code", () => {
  it("keeps the letters, digits, space and hyphen codes are made of", () => {
    expect(sanitizeZip("EC1A 1BB")).toBe("EC1A 1BB");
    expect(sanitizeZip("962-0011")).toBe("962-0011");
    expect(sanitizeZip("75.001")).toBe("75001");
    expect(sanitizeZip("1".repeat(30))).toHaveLength(12);
  });

  it("accepts international formats and rejects the implausible", () => {
    for (const z of ["75001", "8001", "EC1A 1BB", "K1A 0B1"]) expect(isValidZip(z)).toBe(true);
    for (const z of ["", "12", "abcd"]) expect(isValidZip(z)).toBe(false);
  });
});

describe("sanitizePlace", () => {
  it("allows a longer value than a person's name", () => {
    expect(sanitizePlace("a".repeat(200))).toHaveLength(85);
  });
});
