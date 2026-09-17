/**
 * OIP renders-token fallback resolution (#309, OIP#6).
 *
 * Order: exact node_type registration beats the renders token, the token
 * beats the default, an unrecognised token falls through to the default
 * (undefined), and with no server data resolution keeps today's
 * exact-key-only behavior.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getNodeRenderer,
  nodeTypes,
  primeRendersTokenMap,
  registerNodeRenderer,
  resetRendersTokenMapForTests,
  resolveNodeRenderer,
  setRendersTokenMap,
  unregisterNodeRenderer,
} from "./registry";

const chartRenderer = getNodeRenderer("chart");
if (!chartRenderer) throw new Error("chart renderer must be registered");

afterEach(() => {
  resetRendersTokenMapForTests();
  unregisterNodeRenderer("graphtracer:chart_series");
  vi.unstubAllGlobals();
});

describe("resolveNodeRenderer", () => {
  it("resolves an unknown node_type through its renders token", () => {
    setRendersTokenMap(new Map([["graphtracer:chart_series", "chart"]]));
    expect(resolveNodeRenderer("graphtracer:chart_series")).toBe(chartRenderer);
    // The nodeTypes proxy ReactFlow consumes agrees.
    expect(nodeTypes["graphtracer:chart_series"]).toBe(chartRenderer);
    expect("graphtracer:chart_series" in nodeTypes).toBe(true);
  });

  it("prefers an exact registration over the renders token", () => {
    const exact = () => null;
    registerNodeRenderer("graphtracer:chart_series", exact);
    setRendersTokenMap(new Map([["graphtracer:chart_series", "chart"]]));
    expect(resolveNodeRenderer("graphtracer:chart_series")).toBe(exact);
  });

  it("falls through to default on an unrecognised token", () => {
    setRendersTokenMap(
      new Map([["graphtracer:chart_series", "no-such-renderer"]]),
    );
    expect(resolveNodeRenderer("graphtracer:chart_series")).toBeUndefined();
    expect(nodeTypes["graphtracer:chart_series"]).toBeUndefined();
    expect("graphtracer:chart_series" in nodeTypes).toBe(false);
  });

  it("keeps exact-key-only behavior with no server data", () => {
    setRendersTokenMap(null);
    expect(resolveNodeRenderer("graphtracer:chart_series")).toBeUndefined();
    expect(resolveNodeRenderer("chart")).toBe(chartRenderer);
  });
});

describe("primeRendersTokenMap", () => {
  it("builds the map from /api/node-types and ignores junk entries", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify([
            { name: "graphtracer:chart_series", renders: "chart" },
            { name: "fact", renders: null },
            { name: "", renders: "chart" },
            { renders: "chart" },
          ]),
          { status: 200 },
        ),
      ),
    );
    await primeRendersTokenMap();
    expect(resolveNodeRenderer("graphtracer:chart_series")).toBe(chartRenderer);
    // Exact registrations with a null token are untouched.
    expect(resolveNodeRenderer("fact")).toBe(getNodeRenderer("fact"));
  });

  it("tolerates a failed fetch and keeps today's behavior", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("server down");
      }),
    );
    await expect(primeRendersTokenMap()).resolves.toBeUndefined();
    expect(resolveNodeRenderer("graphtracer:chart_series")).toBeUndefined();
  });

  it("fetches once; later calls reuse the cached map", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify([]), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await primeRendersTokenMap();
    await primeRendersTokenMap();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
