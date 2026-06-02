import { afterEach, describe, expect, it, vi } from "vitest";

import { documents } from "./documents";

afterEach(() => {
  vi.unstubAllGlobals();
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
