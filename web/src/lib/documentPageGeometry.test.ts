import { describe, expect, it } from "vitest";

import { bboxToImageRect } from "./bbox";
import { parseDocumentPageGeometry } from "./documentPageGeometry";
import fixture from "./fixtures/documentPageGeometry.json";

describe("document page geometry compatibility", () => {
  it("consumes the actual silver/gold-map producer output", () => {
    expect(parseDocumentPageGeometry(fixture.gold_map.pages_meta)).toEqual({
      1: { width: 600, height: 800 },
      2: { width: 800, height: 600 },
      3: { width: 420, height: 595 },
    });
  });

  it.each(["72", "150", "300"] as const)("scales all source boxes with the real %s-DPI raster", (dpi) => {
    const geometry = parseDocumentPageGeometry(fixture.gold_map.pages_meta);
    for (const page of ["1", "2", "3"] as const) {
      const { width, height } = geometry[Number(page)]!;
      const raster = fixture.rasters[dpi][page];
      for (const bbox of Object.values(fixture.boxes[page])) {
        const before = [...bbox];
        const rect = bboxToImageRect(bbox, width, height, raster.width, raster.height)!;
        expect(rect.x / raster.width).toBeCloseTo(bbox[0]! / width, 12);
        expect(rect.y / raster.height).toBeCloseTo(bbox[1]! / height, 12);
        expect(rect.w / raster.width).toBeCloseTo((bbox[2]! - bbox[0]!) / width, 12);
        expect(rect.h / raster.height).toBeCloseTo((bbox[3]! - bbox[1]!) / height, 12);
        expect(bbox).toEqual(before);
      }
    }
  });

  it("retains explicit compatibility with the old flat width/height shape", () => {
    expect(parseDocumentPageGeometry({ "1": { width: 600, height: 800 } }))
      .toEqual({ 1: { width: 600, height: 800 } });
  });

  it.each([undefined, null, [], {}, { pages: null }, { pages: [] }, { pages: { "1": {} } },
    { page_size: [600, 800] }, { "0": { width: 600, height: 800 } },
    { "1": { width: "600", height: 800 } },
    { bbox_origin: "bottom-left", pages: fixture.gold_map.pages_meta.pages },
  ])("leaves unknown or incompatible metadata unresolved: %j", (raw) => {
    expect(parseDocumentPageGeometry(raw)).toEqual({});
  });

  it.each([null, [], [600], [600, 800, 1], [0, 800], [-600, 800], [600, 0],
    [600, NaN], [Infinity, 800], ["600", 800], { width: 600, height: 800 },
  ])("does not fall back from malformed canonical page_size: %j", (page_size) => {
    expect(parseDocumentPageGeometry({
      pages: { "1": { page_size, width: 600, height: 800 } },
      "1": { width: 600, height: 800 },
    })).toEqual({});
  });
});
