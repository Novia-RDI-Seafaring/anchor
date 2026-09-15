import { describe, expect, it } from "vitest";
import { evidenceState } from "./evidence";

describe("claim-bound evidence", () => {
  const source_ref = { slug: "doc", page: 1, region_id: "pressure" };
  const evidence = { status: "verified", claim: { key: "pressure", value: "42" },
    source_ref, validation: { producer: "anchor_pdfs" } };
  it("uses only G2 normalization and ignores object key order", () => {
    expect(evidenceState({ key: " PRESSURE ", value: " 42 ",
      source_ref: { page: 1, region_id: "pressure", slug: "doc" }, evidence })).toBe("verified");
    for (const value of ["42.0", "42 mm", null, 42]) {
      expect(evidenceState({ key: "Pressure", value, source_ref, evidence })).toBe("stale");
    }
  });
  it("rejects changed source identity and unknown historical bindings", () => {
    expect(evidenceState({ key: "Pressure", value: "42", source_ref: { ...source_ref, page: 2 }, evidence })).toBe("stale");
    expect(evidenceState({ key: "Pressure", value: "42", source_ref })).toBe("unverified");
    expect(evidenceState({ key: "Pressure", value: "42", evidence })).toBe("none");
  });
  it("does not infer verification when text returns to its old value", () => {
    expect(evidenceState({ key: "Pressure", value: "42", source_ref,
      evidence: { ...evidence, status: "stale" } })).toBe("stale");
  });
});
