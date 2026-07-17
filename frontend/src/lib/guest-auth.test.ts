import { beforeEach, describe, expect, it } from "vitest";
import { clearGuestSession, readGuestSession, saveGuestSession, type GuestSession } from "./guest-auth";

const STORAGE_KEY = "guest_session";

const validSession: GuestSession = {
  token: "abc123",
  guestId: "guest-1",
  expiresAt: Date.now() + 60_000,
};

beforeEach(() => {
  window.localStorage.clear();
});

describe("readGuestSession", () => {
  it("returns null when nothing is stored", () => {
    expect(readGuestSession()).toBeNull();
  });

  it("returns the session that was saved", () => {
    saveGuestSession(validSession);
    expect(readGuestSession()).toEqual(validSession);
  });

  it("returns null and clears storage for an expired session", () => {
    saveGuestSession({ ...validSession, expiresAt: Date.now() - 1 });
    expect(readGuestSession()).toBeNull();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("returns null and clears storage for malformed JSON", () => {
    window.localStorage.setItem(STORAGE_KEY, "{not json");
    expect(readGuestSession()).toBeNull();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("returns null and clears storage when a required field is missing", () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ token: "abc123", expiresAt: Date.now() + 60_000 })
    );
    expect(readGuestSession()).toBeNull();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});

describe("saveGuestSession", () => {
  it("writes the session to localStorage as JSON", () => {
    saveGuestSession(validSession);
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY)!)).toEqual(validSession);
  });

  it("overwrites a previously saved session", () => {
    saveGuestSession(validSession);
    const next = { ...validSession, token: "new-token" };
    saveGuestSession(next);
    expect(readGuestSession()).toEqual(next);
  });
});

describe("clearGuestSession", () => {
  it("removes a stored session", () => {
    saveGuestSession(validSession);
    clearGuestSession();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});
