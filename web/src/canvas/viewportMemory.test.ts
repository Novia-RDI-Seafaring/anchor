import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { loadViewport, saveViewport } from "./viewportMemory";

describe("viewport memory", () => {
  // The test environment's storage has no methods; a plain map stands in.
  const original = Object.getOwnPropertyDescriptor(window, "localStorage");
  beforeEach(() => {
    const store = new Map<string, string>();
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => void store.set(k, v),
      },
    });
  });
  afterEach(() => {
    if (original) Object.defineProperty(window, "localStorage", original);
  });

  it("gives back the view a canvas was left at", () => {
    saveViewport("pump", { x: -120, y: 40, zoom: 1.6 });
    expect(loadViewport("pump")).toEqual({ x: -120, y: 40, zoom: 1.6 });
  });

  it("keeps each canvas's view apart", () => {
    saveViewport("pump", { x: 1, y: 2, zoom: 1 });
    expect(loadViewport("motor")).toBeNull();
  });

  it("ignores a stored view it cannot use", () => {
    window.localStorage.setItem("anchor.canvas-viewport.pump", '{"x":1,"y":2,"zoom":0}');
    expect(loadViewport("pump")).toBeNull();
    window.localStorage.setItem("anchor.canvas-viewport.pump", "not json");
    expect(loadViewport("pump")).toBeNull();
  });
});

describe("viewport memory without storage", () => {
  it("falls back to fitting the canvas", () => {
    expect(() => saveViewport("pump", { x: 0, y: 0, zoom: 1 })).not.toThrow();
  });
});
