import { describe, expect, it } from "vitest";
import type { Region } from "@/api/documents";
import { documentRegionLayers } from "./documentRegionLayers";

// Actual stored geometry from the unchanged Norrhavn datasheet, page 1.
const rangeTable: Region = { id: "r5", kind: "table", bbox: [42.797370471851934, 630.1204282623798, 552.9062672233837, 718.9130259824195] };
const coverText: Region = { id: "r6", kind: "text", bbox: [45.35400000000004, 48.2837487999999, 549.9211057499998, 786.65154325] };

describe("document region paint priority", () => {
  it.each([false, true])("puts the real range table above broad cover text, reversed=%s", (reversed) => {
    const regions = reversed ? [coverText, rangeTable] : [rangeTable, coverText];
    const layers = documentRegionLayers(regions, 595.276, 841.89);
    expect(layers.map((layer) => layer.rid)).toEqual(["r6", "r5"]);
    expect(layers[1]!.region).toBe(rangeTable);
    expect(layers[1]!.rect.y).toBeCloseTo(630.1204282623798 / 841.89 * 100);
    expect(layers[1]!.rect.h).toBeCloseTo((718.9130259824195 - 630.1204282623798) / 841.89 * 100);
  });

  it.each([false, true])("prefers smaller partial overlaps and breaks equal-area ties consistently, reversed=%s", (reversed) => {
    const regions = [
      { id: "wide", bbox: [0, 0, 200, 100] },
      { id: "b", bbox: [150, 50, 250, 150] },
      { id: "a", bbox: [175, 75, 275, 175] },
    ];
    const layers = documentRegionLayers(reversed ? [...regions].reverse() : regions, 600, 800);
    expect(layers.map((layer) => layer.rid)).toEqual(["wide", "a", "b"]);
  });

  it("keeps original fallback IDs, region payloads and input order while sorting", () => {
    const regions = [{ bbox: [10, 20, 30, 40] }, { id: "broad", bbox: [0, 0, 600, 800] }, {}, { bbox: [100, 200, 200, 400] }];
    const original = structuredClone(regions);
    const layers = documentRegionLayers(regions, 600, 800);
    expect(layers.map((layer) => layer.rid)).toEqual(["broad", "r3", "r0"]);
    expect(layers[2]!.region).toBe(regions[0]);
    expect(layers[2]!.region.bbox).toBe(regions[0]!.bbox);
    expect(regions).toEqual(original);
  });

  it("omits unusable hit areas without renumbering later regions", () => {
    const regions = [{ bbox: [0, 0, 0, 20] }, { bbox: [0, 0, Number.NaN, 20] }, { bbox: [0, 0, Number.POSITIVE_INFINITY, 20] }, { bbox: [10, 20, 30] }, { bbox: [10, 20, 30, 40] }];
    expect(documentRegionLayers(regions, 600, 800).map((layer) => layer.rid)).toEqual(["r4"]);
    expect(documentRegionLayers(regions, 0, 800)).toEqual([]);
    expect(documentRegionLayers(regions, 600, 0)).toEqual([]);
  });
});
