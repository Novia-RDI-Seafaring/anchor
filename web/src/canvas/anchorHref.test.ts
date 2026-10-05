/**
 * `anchor:` links — the prose form of a source_ref.
 */
import { describe, expect, it } from "vitest";

import { describeRef, formatAnchorHref, isAnchorHref, parseAnchorHref } from "./anchorHref";

describe("parseAnchorHref", () => {
  it("reads a document and a page", () => {
    expect(parseAnchorHref("anchor:lkh-5?page=3")).toEqual({ slug: "lkh-5", page: 3 });
  });

  it("reads the selectors that point below a region", () => {
    expect(parseAnchorHref("anchor:lkh-5?page=3&region=r2")).toMatchObject({ region_id: "r2" });
    expect(parseAnchorHref("anchor:lkh-5?page=3&item=p3-i0")).toMatchObject({ item_id: "p3-i0" });
    expect(parseAnchorHref("anchor:lkh-5?page=3&cell=4,1")).toMatchObject({
      cell: { row: 4, col: 1 },
    });
    expect(parseAnchorHref("anchor:lkh-5?page=3&bbox=10,20,80,40")).toMatchObject({
      bbox: [10, 20, 80, 40],
    });
  });

  it("accepts the long-form spelling and a percent-encoded slug", () => {
    expect(parseAnchorHref("anchor://my%20doc?page=1")).toEqual({ slug: "my doc", page: 1 });
  });

  it("also accepts the source_ref field names", () => {
    expect(parseAnchorHref("anchor:d?page=2&region_id=r1&item_id=p2-i3")).toMatchObject({
      region_id: "r1",
      item_id: "p2-i3",
    });
  });

  it("refuses a ref that points nowhere", () => {
    // No document, no page, or a page that isn't a page.
    expect(parseAnchorHref("anchor:?page=3")).toBeNull();
    expect(parseAnchorHref("anchor:lkh-5")).toBeNull();
    expect(parseAnchorHref("anchor:lkh-5?page=0")).toBeNull();
    expect(parseAnchorHref("anchor:lkh-5?page=two")).toBeNull();
    expect(parseAnchorHref("anchor:a/b?page=1")).toBeNull();
  });

  it("drops a selector it cannot read rather than guessing", () => {
    const ref = parseAnchorHref("anchor:d?page=1&cell=4&bbox=1,2,3");
    expect(ref).toEqual({ slug: "d", page: 1 });
  });

  it("is not a parser for other links", () => {
    expect(parseAnchorHref("https://example.com")).toBeNull();
    expect(parseAnchorHref(undefined)).toBeNull();
    expect(isAnchorHref("https://example.com")).toBe(false);
    expect(isAnchorHref("ANCHOR:d?page=1")).toBe(true);
  });
});

describe("formatAnchorHref", () => {
  it("round-trips a ref through its written form", () => {
    const ref = { slug: "lkh-5", page: 3, region_id: "r2", cell: { row: 4, col: 1 } };
    expect(parseAnchorHref(formatAnchorHref(ref))).toEqual(ref);
  });
});

describe("describeRef", () => {
  it("names the tightest selector it has", () => {
    expect(describeRef({ slug: "d", page: 3 })).toBe("d · page 3");
    expect(describeRef({ slug: "d", page: 3, region_id: "r2" })).toContain("region r2");
    expect(describeRef({ slug: "d", page: 3, region_id: "r2", item_id: "p3-i0" })).toContain(
      "item p3-i0",
    );
    expect(
      describeRef({ slug: "d", page: 3, item_id: "p3-i0", cell: { row: 1, col: 2 } }),
    ).toContain("cell 1,2");
  });
});

describe("a reference to more than one place", () => {
  it("reads the extra places off the link", () => {
    // One claim, evidenced twice: the value in the table and the callout
    // naming that dimension on the drawing beside it.
    const ref = parseAnchorHref(
      "anchor:lkh?page=3&region=r2&cell=1,2&also=p3/r1/item:p3-i6",
    );
    expect(ref).toMatchObject({
      slug: "lkh",
      page: 3,
      region_id: "r2",
      cell: { row: 1, col: 2 },
      also: ["p3/r1/item:p3-i6"],
    });
  });

  it("takes as many extra places as the link names", () => {
    const ref = parseAnchorHref(
      "anchor:lkh?page=3&region=r2&also=p3/r1/item:p3-i6&also=p3/r1/item:p3-i9",
    );
    expect(ref?.also).toEqual(["p3/r1/item:p3-i6", "p3/r1/item:p3-i9"]);
  });

  it("leaves a single-place link exactly as it was", () => {
    // Every reference written before this existed still has to parse the same.
    const ref = parseAnchorHref("anchor:lkh?page=3&region=r2&cell=1,2");
    expect(ref?.also).toBeUndefined();
  });

  it("survives the round trip back into a link", () => {
    const href = formatAnchorHref({
      slug: "lkh",
      page: 3,
      region_id: "r2",
      also: ["p3/r1/item:p3-i6"],
    });
    expect(parseAnchorHref(href)?.also).toEqual(["p3/r1/item:p3-i6"]);
  });

  it("drops empty extras rather than carrying a place that names nothing", () => {
    const ref = parseAnchorHref("anchor:lkh?page=3&also=&also=%20");
    expect(ref?.also).toBeUndefined();
  });
});
