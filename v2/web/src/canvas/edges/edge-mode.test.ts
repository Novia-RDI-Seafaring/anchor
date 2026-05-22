import { describe, expect, it } from "vitest";

import { pickEdgeMode, type EdgeForMode, type HoveredSourceRef } from "./edge-mode";

const evidenceEdge = (sourceRef: Record<string, unknown>, targetDocSlug = "lkh"): EdgeForMode => ({
  edge_type: "anchored",
  data: { kind: "evidence", source_ref: sourceRef },
  targetDocSlug,
});

describe("pickEdgeMode", () => {
  it("floats an evidence edge when nothing is hovered", () => {
    const edge = evidenceEdge({ page: 2, region_id: "r4" });
    expect(pickEdgeMode(edge, null)).toBe("floating");
  });

  it("anchors an evidence edge when the hovered source_ref matches slug+page+region_id", () => {
    const edge = evidenceEdge({ page: 2, region_id: "r4" });
    const hovered: HoveredSourceRef = { slug: "lkh", page: 2, region_id: "r4" };
    expect(pickEdgeMode(edge, hovered)).toBe("anchored");
  });

  it("floats an evidence edge when the hovered slug is for a different document", () => {
    const edge = evidenceEdge({ page: 2, region_id: "r4" }, "lkh");
    const hovered: HoveredSourceRef = { slug: "other-doc", page: 2, region_id: "r4" };
    expect(pickEdgeMode(edge, hovered)).toBe("floating");
  });

  it("floats an evidence edge when the page differs", () => {
    const edge = evidenceEdge({ page: 2, region_id: "r4" });
    const hovered: HoveredSourceRef = { slug: "lkh", page: 3, region_id: "r4" };
    expect(pickEdgeMode(edge, hovered)).toBe("floating");
  });

  it("floats an evidence edge when both region_ids are set and they disagree", () => {
    const edge = evidenceEdge({ page: 2, region_id: "r4" });
    const hovered: HoveredSourceRef = { slug: "lkh", page: 2, region_id: "r9" };
    expect(pickEdgeMode(edge, hovered)).toBe("floating");
  });

  it("anchors when the edge has no region_id but slug+page still match (region-agnostic match)", () => {
    const edge = evidenceEdge({ page: 2 });
    const hovered: HoveredSourceRef = { slug: "lkh", page: 2, region_id: "r4" };
    expect(pickEdgeMode(edge, hovered)).toBe("anchored");
  });

  it("anchors when the hovered ref has no region_id but slug+page match", () => {
    // Row hover broadcasts page+region_id; region hover broadcasts the
    // same; doc-node hover may broadcast only page. Either way the edge's
    // own region_id is enough to identify it.
    const edge = evidenceEdge({ page: 2, region_id: "r4" });
    const hovered: HoveredSourceRef = { slug: "lkh", page: 2 };
    expect(pickEdgeMode(edge, hovered)).toBe("anchored");
  });

  it("keeps non-evidence anchored edges (e.g. SysML ports) in anchored mode regardless of hover", () => {
    const edge: EdgeForMode = {
      edge_type: "anchored",
      data: { kind: "interface-connection" },
    };
    expect(pickEdgeMode(edge, null)).toBe("anchored");
    expect(pickEdgeMode(edge, { slug: "x", page: 1 })).toBe("anchored");
  });

  it("keeps loose graph edges floating regardless of hover", () => {
    const edge: EdgeForMode = { edge_type: "floating", data: {} };
    expect(pickEdgeMode(edge, null)).toBe("floating");
    expect(pickEdgeMode(edge, { slug: "x", page: 1, region_id: "r4" })).toBe("floating");
  });

  it("floats evidence edges with no stored source_ref (defensive — shouldn't happen, but doesn't crash)", () => {
    const edge: EdgeForMode = {
      edge_type: "anchored",
      data: { kind: "evidence" },
      targetDocSlug: "lkh",
    };
    expect(pickEdgeMode(edge, { slug: "lkh", page: 2 })).toBe("floating");
  });

  // The Miro-style edge editor introduces three new routing modes
  // (smooth / step / straight). pickEdgeMode must preserve them for
  // non-evidence edges and treat them as the "rest state" for evidence
  // edges — hover still flips to anchored, but the user's chosen routing
  // survives when not hovered.
  it("preserves smooth/step/straight for non-evidence edges", () => {
    expect(pickEdgeMode({ edge_type: "smooth", data: {} }, null)).toBe("smooth");
    expect(pickEdgeMode({ edge_type: "step", data: {} }, null)).toBe("step");
    expect(pickEdgeMode({ edge_type: "straight", data: {} }, null)).toBe("straight");
  });

  it("preserves smooth routing for an evidence edge when nothing is hovered", () => {
    const edge: EdgeForMode = {
      edge_type: "smooth",
      data: { kind: "evidence", source_ref: { page: 2, region_id: "r4" } },
      targetDocSlug: "lkh",
    };
    expect(pickEdgeMode(edge, null)).toBe("smooth");
  });

  it("still flips a user-routed (smooth) evidence edge to anchored on hover match", () => {
    // Critical row-handle UX: even if the user picked smooth for routing,
    // hovering the matching row swaps to anchored so the row→region wire
    // becomes visible. Otherwise the cross-component highlight would
    // break for any edge a user customised the routing on.
    const edge: EdgeForMode = {
      edge_type: "smooth",
      data: { kind: "evidence", source_ref: { page: 2, region_id: "r4" } },
      targetDocSlug: "lkh",
    };
    const hovered: HoveredSourceRef = { slug: "lkh", page: 2, region_id: "r4" };
    expect(pickEdgeMode(edge, hovered)).toBe("anchored");
  });

  it("returns 'smooth' (user pick) when an evidence edge's hover doesn't match", () => {
    const edge: EdgeForMode = {
      edge_type: "step",
      data: { kind: "evidence", source_ref: { page: 2, region_id: "r4" } },
      targetDocSlug: "lkh",
    };
    // Page mismatch — rest state of `step` survives.
    expect(pickEdgeMode(edge, { slug: "lkh", page: 9 })).toBe("step");
  });

  it("normalises unknown edge_type strings to 'floating' (defensive)", () => {
    const edge: EdgeForMode = { edge_type: "wibble", data: {} };
    expect(pickEdgeMode(edge, null)).toBe("floating");
  });
});
