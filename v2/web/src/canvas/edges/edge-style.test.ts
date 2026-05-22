/**
 * edge-style unit tests — pinning the user-pickable edge style resolution
 * the EdgeContextToolbar / EdgeContextMenu / Routed* edges all consume.
 */
import { describe, expect, it } from "vitest";

import {
  DEFAULT_EDGE_STROKE,
  resolveEdgeUserStyle,
  userMarkerUrls,
} from "./edge-style";
import { MARKER_IDS } from "./markers";

describe("resolveEdgeUserStyle", () => {
  it("returns defaults for empty data", () => {
    const s = resolveEdgeUserStyle({});
    expect(s.strokeColor).toBe(DEFAULT_EDGE_STROKE);
    expect(s.strokeStyle).toBe("solid");
    expect(s.strokeDasharray).toBeUndefined();
    expect(s.startMarker).toBe("none");
    expect(s.endMarker).toBe("arrow");
    expect(s.locked).toBe(false);
    expect(s.waypoints).toEqual([]);
    expect(s.borderRadius).toBeUndefined();
  });

  it("uses the stored fields when present", () => {
    const s = resolveEdgeUserStyle({
      stroke_color: "rgb(225, 29, 72)",
      stroke_style: "dashed",
      start_marker: "circle",
      end_marker: "none",
      locked: true,
      borderRadius: 0,
      waypoints: [{ x: 100, y: 200 }],
    });
    expect(s.strokeColor).toBe("rgb(225, 29, 72)");
    expect(s.strokeStyle).toBe("dashed");
    expect(s.strokeDasharray).toBe("6 4");
    expect(s.startMarker).toBe("circle");
    expect(s.endMarker).toBe("none");
    expect(s.locked).toBe(true);
    expect(s.borderRadius).toBe(0);
    expect(s.waypoints).toEqual([{ x: 100, y: 200 }]);
  });

  it("falls back to defaults when fields are nonsense", () => {
    const s = resolveEdgeUserStyle({
      stroke_color: 12 as unknown as string,
      stroke_style: "wibble" as unknown as "solid",
      start_marker: "lava" as unknown as "none",
      waypoints: [{ x: "a", y: 0 }, null, { x: 1, y: 2 }] as unknown[],
    });
    expect(s.strokeColor).toBe(DEFAULT_EDGE_STROKE);
    expect(s.strokeStyle).toBe("solid");
    expect(s.startMarker).toBe("none");
    expect(s.waypoints).toEqual([{ x: 1, y: 2 }]);
  });

  it("maps dotted to a `1 2` dasharray (matches the Miro line-style chip)", () => {
    const s = resolveEdgeUserStyle({ stroke_style: "dotted" });
    expect(s.strokeDasharray).toBe("2 4");
  });
});

describe("userMarkerUrls", () => {
  it("returns user markers when end=arrow is requested", () => {
    const { markerStart, markerEnd } = userMarkerUrls({ start: "none", end: "arrow", selected: false });
    expect(markerStart).toBeUndefined();
    expect(markerEnd).toBe(`url(#${MARKER_IDS.userArrow})`);
  });

  it("swaps in the selected variants when selected=true", () => {
    const { markerStart, markerEnd } = userMarkerUrls({ start: "circle", end: "arrow", selected: true });
    expect(markerStart).toBe(`url(#${MARKER_IDS.userCircleSel})`);
    expect(markerEnd).toBe(`url(#${MARKER_IDS.userArrowSel})`);
  });

  it("returns undefined for both ends when both are 'none'", () => {
    const { markerStart, markerEnd } = userMarkerUrls({ start: "none", end: "none", selected: false });
    expect(markerStart).toBeUndefined();
    expect(markerEnd).toBeUndefined();
  });
});
