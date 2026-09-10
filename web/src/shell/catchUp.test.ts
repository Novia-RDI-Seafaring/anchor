/**
 * Catch-up bookkeeping (#325): last-seen persistence + the show decision.
 * Storage failures (private mode, blocked site data) must degrade to
 * "no memory" — never throw into the render path.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  lastSeenKey,
  readLastSeen,
  shouldShowCatchUp,
  writeLastSeen,
} from "./catchUp";
import { installFakeStorage, installThrowingStorage } from "./testStorage";

let restore: () => void;
let storage: ReturnType<typeof installFakeStorage>["storage"];

beforeEach(() => {
  ({ storage, restore } = installFakeStorage());
});

afterEach(() => {
  restore();
});

describe("readLastSeen / writeLastSeen", () => {
  it("round-trips a version per slug", () => {
    writeLastSeen("plant", 7);
    writeLastSeen("pump", 3);
    expect(readLastSeen("plant")).toBe(7);
    expect(readLastSeen("pump")).toBe(3);
    // Namespaced per slug — no cross-canvas leakage.
    expect(storage.getItem(lastSeenKey("plant"))).toBe("7");
  });

  it("answers null when nothing is stored", () => {
    expect(readLastSeen("ghost")).toBeNull();
  });

  it("answers null for garbage or negative stored values", () => {
    storage.setItem(lastSeenKey("plant"), "not-a-number");
    expect(readLastSeen("plant")).toBeNull();
    storage.setItem(lastSeenKey("plant"), "-4");
    expect(readLastSeen("plant")).toBeNull();
  });

  it("survives a throwing localStorage", () => {
    restore();
    ({ restore } = installThrowingStorage());
    expect(() => writeLastSeen("plant", 5)).not.toThrow();
    expect(readLastSeen("plant")).toBeNull();
  });

  it("survives a method-less localStorage stub", () => {
    restore();
    const swap = Object.getOwnPropertyDescriptor(window, "localStorage");
    Object.defineProperty(window, "localStorage", {
      value: {},
      configurable: true,
    });
    try {
      expect(() => writeLastSeen("plant", 5)).not.toThrow();
      expect(readLastSeen("plant")).toBeNull();
    } finally {
      if (swap) Object.defineProperty(window, "localStorage", swap);
    }
    ({ restore } = installFakeStorage());
  });
});

describe("shouldShowCatchUp", () => {
  it("shows only when we have a memory and the canvas moved past it", () => {
    expect(shouldShowCatchUp(3, 5)).toBe(true);
  });

  it("stays quiet on a first visit (no stored value)", () => {
    expect(shouldShowCatchUp(null, 5)).toBe(false);
  });

  it("stays quiet when caught up or ahead", () => {
    expect(shouldShowCatchUp(5, 5)).toBe(false);
    expect(shouldShowCatchUp(9, 5)).toBe(false);
  });
});
