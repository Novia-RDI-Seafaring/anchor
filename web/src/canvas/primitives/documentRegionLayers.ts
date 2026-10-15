import type { Region } from "@/api/documents";
import { bboxToImageRect } from "@/lib/bbox";

/** Paint broad hit areas first so a smaller overlapping source wins. */
export function documentRegionLayers(regions: Region[], pageW: number, pageH: number) {
  return regions.flatMap((region, index) => {
    const rect = bboxToImageRect(region.bbox, pageW, pageH, 100, 100);
    if (!rect || !Object.values(rect).every(Number.isFinite) || rect.w <= 0 || rect.h <= 0) return [];
    // Keep the source index: changing paint order must not rename legacy refs.
    return [{ region, rid: region.id ?? `r${index}`, rect }];
  }).sort((a, b) => b.rect.w * b.rect.h - a.rect.w * a.rect.h || a.rid.localeCompare(b.rid));
}
