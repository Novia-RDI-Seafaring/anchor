import { afterEach, describe, expect, it, vi } from "vitest";

import { documents } from "./documents";

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
