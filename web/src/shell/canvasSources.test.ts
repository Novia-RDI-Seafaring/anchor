import { describe, expect, it } from "vitest";

import { canvasSources } from "./canvasSources";

describe("canvasSources", () => {
  it("deduplicates node, row, card and edge sources without needing a document card", () => {
    const sources = canvasSources({
      fact: { node_type: "fact", data: { source_ref: { slug: "guide", page: 2 } } },
      table: { node_type: "spec", data: { rows: [
        { source_ref: { slug: "guide", page: 3 } },
        { source_ref: { slug: "datasheet", page: 1, bbox: [1, 2, 3, 4] } },
      ] } },
      card: { node_type: "document", data: { slug: "guide" } },
    }, {
      evidence: { target: "fact", data: { source_ref: { slug: "appendix", page: 4 } } },
    });
    expect(sources.map((source) => source.slug)).toEqual(["appendix", "datasheet", "guide"]);
    expect(sources[1]?.ref).toEqual({ slug: "datasheet", page: 1, bbox: [1, 2, 3, 4] });
    expect(sources[2]?.ref?.page).toBe(2);
  });

  it("retains legacy source_doc_slug and evidence refs that inherit a document target", () => {
    expect(canvasSources({
      table: { node_type: "spec", data: {
        source_doc_slug: "legacy",
        source_ref: { page: 1 },
        rows: [{ source_ref: { page: 2 } }, { source_ref: { slug: "other", page: 3 } }],
      } },
      card: { node_type: "document", data: { slug: "card" } },
    }, { evidence: { target: "card", data: { source_ref: { page: 4 } } } }))
      .toEqual([
        { slug: "card", ref: { slug: "card", page: 4 } },
        { slug: "legacy", ref: { slug: "legacy", page: 1 } },
        { slug: "other", ref: { slug: "other", page: 3 } },
      ]);
  });

  it("ignores unrelated slugs and malformed or non-PDF references", () => {
    expect(canvasSources({
      canvas: { node_type: "canvas", data: { slug: "child-canvas" } },
      cad: { node_type: "cad:model", data: { slug: "model", cad_slug: "model" } },
      node: { node_type: "fact", data: {
        source_ref: { slug: " ", page: 1 },
        rows: [null, "text", { source_ref: { kind: "fmu-variable", slug: "simulation" } }],
        arbitrary: { source_ref: { slug: "unrelated", page: 1 } },
      } },
    }, {})).toEqual([]);
  });

  it("keeps named sources with an incomplete locator visible without inventing a page", () => {
    expect(canvasSources({
      fact: { node_type: "fact", data: { source_ref: { slug: "missing" } } },
    }, {})).toEqual([{ slug: "missing", ref: undefined }]);
  });

  it("resolves legacy document IDs only through document cards and normalizes region aliases", () => {
    const sources = canvasSources({
      card: { node_type: "document", data: { slug: "guide" } },
      child: { node_type: "canvas", data: { slug: "other-canvas" } },
      fact: { node_type: "fact", data: { source_ref: { doc_id: "card", page: 2, source_region_id: "r2" } } },
      table: { node_type: "spec", data: {
        source_doc_node_id: "card", rows: [{ source_ref: { page: 3 } }],
      } },
      invalid: { node_type: "fact", data: { source_ref: { doc_id: "child", page: 1 } } },
    }, {});
    expect(sources).toEqual([{
      slug: "guide", ref: { slug: "guide", doc_id: "card", page: 2, source_region_id: "r2", region_id: "r2" },
    }]);
  });

  it("lets a row override the inherited document without borrowing its region", () => {
    const sources = canvasSources({
      table: { node_type: "spec", data: {
        source_ref: { slug: "guide", page: 1 }, source_region_id: "guide-region",
        rows: [
          { source_ref: { page: 2 } },
          { source_ref: { slug: "other", page: 3 } },
        ],
      } },
    }, {});
    expect(sources.map((source) => source.slug)).toEqual(["guide", "other"]);
    expect(sources[0]?.ref?.region_id).toBe("guide-region");
    expect(sources[1]?.ref).toEqual({ slug: "other", page: 3 });
  });
});
