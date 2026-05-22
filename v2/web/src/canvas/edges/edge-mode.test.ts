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
});
