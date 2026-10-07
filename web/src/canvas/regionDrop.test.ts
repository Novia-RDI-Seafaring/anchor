/**
 * A section dragged onto the canvas. The failure this guards against: a
 * drawing arriving as a card of no rows.
 */
import { describe, expect, it } from "vitest";

import { regionDropPayload } from "@/canvas/regionDrop";

describe("what a dragged section becomes", () => {
  it("makes a diagram a picture cut from the page", () => {
    const p = regionDropPayload({
      slug: "lkh",
      page: 3,
      region: { id: "r1", kind: "diagram", title: "Dimensions", bbox: [56, 58, 291, 189] },
      documentNodeId: "doc1",
    })!;
    expect(p.node_type).toBe("image");
    expect(p.label).toBe("Dimensions");
    expect(p.data.source_ref).toEqual({
      slug: "lkh",
      coord_origin: "top-left",
      kind: "pdf-page-bbox",
      page: 3,
      bbox: [56, 58, 291, 189],
      region_id: "r1",
    });
    // The drop still joins the picture to the card it came from.
    expect(p.data.source_doc_node_id).toBe("doc1");
  });

  it("keeps a table a spec card, as before", () => {
    const p = regionDropPayload({
      slug: "lkh",
      page: 3,
      region: { id: "r2", kind: "table", title: "Pump specific measures (mm)", bbox: [55, 215, 552, 277] },
    })!;
    expect(p.node_type).toBe("spec");
    expect(p.data.source_region_id).toBe("r2");
    // Wide enough to read the table's picture, and no paragraph of it.
    expect(p.width).toBe(795);
    expect(p.data.width).toBe(795);
    expect(p.data.description).toBeUndefined();
  });

  it("refuses a section with no box to point at", () => {
    expect(regionDropPayload({ slug: "lkh", page: 1, region: { id: "x", kind: "text" } })).toBeNull();
  });
});
