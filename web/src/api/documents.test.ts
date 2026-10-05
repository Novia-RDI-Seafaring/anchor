import { afterEach, describe, expect, it, vi } from "vitest";

import { documents, refHasSelector } from "./documents";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("documents.locate", () => {
  it("requests the locate endpoint with query (+ optional bbox) and returns quads", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        slug: "alfa-laval-lkh",
        page: 2,
        query: "600 kPa",
        quads: [[210, 455, 360, 438]],
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    const quads = await documents.locate("alfa-laval-lkh", 2, "600 kPa", [50, 480, 550, 410]);

    expect(quads).toEqual([[210, 455, 360, 438]]);
    const url = (fetchMock.mock.calls[0] as unknown[] | undefined)?.[0] as string ?? "";
    expect(url).toContain("/api/documents/alfa-laval-lkh/pages/2/locate");
    expect(url).toContain("query=600+kPa");
    expect(url).toContain("bbox=50%2C480%2C550%2C410");
  });

  it("omits the bbox param when none is given", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ quads: [] }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    await documents.locate("alfa-laval-lkh", 1, "LKH-5");

    const url = (fetchMock.mock.calls[0] as unknown[] | undefined)?.[0] as string ?? "";
    expect(url).not.toContain("bbox=");
  });

  it("falls back to an empty list (never throws) when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false,
      status: 404,
      text: async () => "not found",
    })));

    const quads = await documents.locate("nope", 1, "LKH-5");
    expect(quads).toEqual([]);
  });

  it("returns an empty list when the response has no quads array", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ slug: "x", page: 1, query: "y" }),
    })));

    const quads = await documents.locate("x", 1, "y");
    expect(quads).toEqual([]);
  });
});

describe("refHasSelector", () => {
  it("is false for refs without below-region selectors (the unchanged region path)", () => {
    expect(refHasSelector(undefined)).toBe(false);
    expect(refHasSelector(null)).toBe(false);
    expect(refHasSelector({ slug: "d", page: 2, region_id: "r1", bbox: [0, 0, 10, 10] })).toBe(false);
    // A partial cell is not a selector — the resolver needs both row and col.
    expect(refHasSelector({ page: 2, cell: { row: 1 } })).toBe(false);
  });

  it("is true for a cell selector or an item_id", () => {
    expect(refHasSelector({ page: 2, cell: { row: 0, col: 1 } })).toBe(true);
    expect(refHasSelector({ page: 2, item_id: "p2-i1" })).toBe(true);
  });
});

describe("documents.resolveRef", () => {
  it("requests resolve-ref with the ref's page/region/cell and returns the answer", async () => {
    const resolved = {
      slug: "alfa-laval-lkh",
      page: 2,
      bbox: [280, 120, 340, 132],
      precision: "cell",
      region_id: "r4",
      cell: { row: 0, col: 1 },
    };
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => resolved,
    }));
    vi.stubGlobal("fetch", fetchMock);

    const out = await documents.resolveRef("alfa-laval-lkh", {
      page: 2,
      region_id: "r4",
      bbox: [50, 40, 550, 200],
      cell: { row: 0, col: 1 },
    });

    expect(out).toEqual(resolved);
    const url = (fetchMock.mock.calls[0] as unknown[] | undefined)?.[0] as string ?? "";
    expect(url).toContain("/api/documents/alfa-laval-lkh/resolve-ref");
    expect(url).toContain("page=2");
    expect(url).toContain("region_id=r4");
    expect(url).toContain("row=0");
    expect(url).toContain("col=1");
  });

  it("passes an item_id selector through", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ slug: "d", page: 2, bbox: [1, 2, 3, 4], precision: "item" }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    await documents.resolveRef("d", { page: 2, item_id: "p2-i1" });

    const url = (fetchMock.mock.calls[0] as unknown[] | undefined)?.[0] as string ?? "";
    expect(url).toContain("item_id=p2-i1");
    expect(url).not.toContain("row=");
  });

  it("resolves to null (never throws) on 404 so callers fall back to the ref's own bbox", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false,
      status: 404,
      text: async () => "unresolvable ref",
    })));

    const out = await documents.resolveRef("d", { page: 2, cell: { row: 0, col: 1 } });
    expect(out).toBeNull();
  });

  it("resolves to null when the answer has no usable bbox", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ slug: "d", page: 2, precision: "region" }),
    })));

    const out = await documents.resolveRef("d", { page: 2, cell: { row: 0, col: 1 } });
    expect(out).toBeNull();
  });
});

describe("documents.regions", () => {
  it("uses approximate_bbox when a gold region has no bbox field", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        slug: "alfa-laval-lkh",
        pages: {
          "2": [
            {
              id: "r9",
              title: "Temperature",
              approximate_bbox: [55.61, 352.92, 552.87, 394.66],
            },
          ],
        },
      }),
    })));

    const regions = await documents.regions("alfa-laval-lkh", 2);

    expect(regions).toHaveLength(1);
    expect(regions[0]?.bbox).toEqual([55.61, 352.92, 552.87, 394.66]);
  });
});
