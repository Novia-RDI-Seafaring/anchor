import { describe, expect, it } from "vitest";

import { MARKER_IDS, arrowheadFor, markerUrls } from "./markers";

describe("arrowheadFor", () => {
  it("returns the inheritance style: solid line, hollow triangle at TARGET", () => {
    const s = arrowheadFor("inheritance");
    expect(s.markerStartId).toBeNull();
    expect(s.markerEndId).toBe(MARKER_IDS.hollowTriangle);
    expect(s.strokeDasharray).toBe("");
    expect(s.labelOverride).toBeNull();
  });

  it("returns the subset style: dashed line, hollow triangle at TARGET", () => {
    const s = arrowheadFor("subset");
    expect(s.markerEndId).toBe(MARKER_IDS.hollowTriangle);
    expect(s.strokeDasharray).not.toBe("");
  });

  it("returns the composition style: filled diamond at SOURCE, open arrow at TARGET", () => {
    const s = arrowheadFor("composition");
    expect(s.markerStartId).toBe(MARKER_IDS.filledDiamond);
    expect(s.markerEndId).toBe(MARKER_IDS.openArrow);
    expect(s.strokeDasharray).toBe("");
  });

  it("returns the satisfy style: dashed line, open arrow, «satisfy» label", () => {
    const s = arrowheadFor("satisfy");
    expect(s.markerEndId).toBe(MARKER_IDS.openArrow);
    expect(s.strokeDasharray).not.toBe("");
    expect(s.labelOverride).toBe("«satisfy»");
  });

  it("returns the redefinition style with a ':>>' label", () => {
    const s = arrowheadFor("redefinition");
    expect(s.markerEndId).toBe(MARKER_IDS.hollowTriangle);
    expect(s.labelOverride).toBe(":>>");
  });

  it("interface-connection has no arrowheads (port-to-port wiring)", () => {
    const s = arrowheadFor("interface-connection");
    expect(s.markerStartId).toBeNull();
    expect(s.markerEndId).toBeNull();
  });

  it("subject is plain (solid, no arrows)", () => {
    const s = arrowheadFor("subject");
    expect(s.markerStartId).toBeNull();
    expect(s.markerEndId).toBeNull();
    expect(s.strokeDasharray).toBe("");
  });

  it("association is the default fallback", () => {
    const s = arrowheadFor("association");
    expect(s.markerEndId).toBe(MARKER_IDS.openArrow);
  });

  it("unknown markers fall back to association", () => {
    const unknown = arrowheadFor("not-a-real-marker" as unknown as "association");
    expect(unknown).toEqual(arrowheadFor("association"));
  });

  it("null/undefined markers fall back to association", () => {
    expect(arrowheadFor(null)).toEqual(arrowheadFor("association"));
    expect(arrowheadFor(undefined)).toEqual(arrowheadFor("association"));
  });
});

describe("markerUrls", () => {
  it("wraps non-null IDs in url(#...) and omits empty ends", () => {
    const urls = markerUrls(arrowheadFor("composition"));
    expect(urls.markerStart).toBe(`url(#${MARKER_IDS.filledDiamond})`);
    expect(urls.markerEnd).toBe(`url(#${MARKER_IDS.openArrow})`);
  });

  it("returns undefined for ends with no marker", () => {
    const urls = markerUrls(arrowheadFor("interface-connection"));
    expect(urls.markerStart).toBeUndefined();
    expect(urls.markerEnd).toBeUndefined();
  });
});
