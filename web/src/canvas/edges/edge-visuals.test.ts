/**
 * edge-visuals unit tests — pinning the quiet-vs-active geometry for
 * evidence/provenance edges (#183). The hover-thicken declutter must only
 * change stroke width / opacity, so these tests assert:
 *
 *   - a quiet evidence edge is thinner than an active one,
 *   - active edges thicken (the hovered provenance path pops),
 *   - the `dimmed` reader only trips for off-path evidence edges,
 *   - non-evidence edges never read as evidence/dimmed.
 */
import { describe, expect, it } from "vitest";

import {
  EVIDENCE_EDGE_ACTIVE_WIDTH,
  EVIDENCE_EDGE_QUIET_WIDTH,
  evidenceStrokeWidth,
  isDimmedEvidence,
  isEvidenceEdge,
} from "./edge-visuals";

describe("evidenceStrokeWidth", () => {
  it("renders quiet edges thinner than active edges", () => {
    expect(EVIDENCE_EDGE_QUIET_WIDTH).toBeLessThan(EVIDENCE_EDGE_ACTIVE_WIDTH);
  });

  it("thickens to the active width on hover-highlight", () => {
    expect(evidenceStrokeWidth(true)).toBe(EVIDENCE_EDGE_ACTIVE_WIDTH);
  });

  it("returns the quiet resting width by default", () => {
    expect(evidenceStrokeWidth(false)).toBe(EVIDENCE_EDGE_QUIET_WIDTH);
  });
});

describe("isDimmedEvidence", () => {
  it("is true only for an evidence edge flagged dimmed", () => {
    expect(isDimmedEvidence({ kind: "evidence", dimmed: true })).toBe(true);
  });

  it("is false for an undimmed evidence edge", () => {
    expect(isDimmedEvidence({ kind: "evidence" })).toBe(false);
  });

  it("is false for a non-evidence edge even when dimmed is set", () => {
    expect(isDimmedEvidence({ kind: "relation", dimmed: true })).toBe(false);
  });
});

describe("isEvidenceEdge", () => {
  it("discriminates on data.kind === 'evidence'", () => {
    expect(isEvidenceEdge({ kind: "evidence" })).toBe(true);
    expect(isEvidenceEdge({ kind: "relation" })).toBe(false);
    expect(isEvidenceEdge(null)).toBe(false);
  });
});
