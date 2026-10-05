/**
 * sourceHighlight.ts — where on a picture cut from a page a hovered
 * reference lands.
 *
 * A row's reference points at a cell in a table and, through `also`, at the
 * letter naming that dimension on the drawing. The source viewer lights both.
 * A picture of that drawing on the canvas is the same page, cut to a box: so
 * the letter's box can be lit there too, by mapping it from page points into
 * the picture's own frame. Boxes outside the cut are dropped rather than
 * clamped, since a mark on the picture's edge would point at the wrong thing.
 */

/** `key` names which place this is, so its mark can travel to the next one. */
export type PagePlace = { page: number; bbox: number[]; key?: string };
/** A box on the picture, in percent of its width and height. */
export type PictureBox = { left: number; top: number; width: number; height: number; key?: string };

function inside(b: number[], crop: number[]): boolean {
  const [x0, y0, x1, y1] = b as [number, number, number, number];
  const [cx0, cy0, cx1, cy1] = crop as [number, number, number, number];
  // The box's centre within the cut is enough: letters sit on the drawing,
  // a stray margin should not make them miss.
  const mx = (x0 + x1) / 2;
  const my = (y0 + y1) / 2;
  return mx >= cx0 && mx <= cx1 && my >= cy0 && my <= cy1;
}

export function boxesOnPicture(crop: PagePlace, places: PagePlace[]): PictureBox[] {
  if (crop.bbox.length !== 4) return [];
  const [cx0, cy0, cx1, cy1] = crop.bbox as [number, number, number, number];
  const w = cx1 - cx0;
  const h = cy1 - cy0;
  if (w <= 0 || h <= 0) return [];
  return places
    .filter((p) => p.page === crop.page && p.bbox.length === 4 && inside(p.bbox, crop.bbox))
    .map((p) => {
      const [x0, y0, x1, y1] = p.bbox as [number, number, number, number];
      return {
        left: ((x0 - cx0) / w) * 100,
        top: ((y0 - cy0) / h) * 100,
        width: ((x1 - x0) / w) * 100,
        height: ((y1 - y0) / h) * 100,
        ...(p.key ? { key: p.key } : {}),
      };
    });
}

/** The places a reference's `also` names, when they carry a box. */
export function placesFromAlso(also: unknown, fallbackPage?: number): PagePlace[] {
  if (!Array.isArray(also)) return [];
  const out: PagePlace[] = [];
  for (const a of also) {
    if (typeof a !== "object" || a === null) continue;
    const r = a as { page?: unknown; bbox?: unknown };
    const page = typeof r.page === "number" ? r.page : fallbackPage;
    if (typeof page !== "number" || !Array.isArray(r.bbox) || r.bbox.length !== 4) continue;
    out.push({ page, bbox: r.bbox.map(Number) });
  }
  return out;
}

/**
 * Whether a hovered reference is the picture's own, and so lights nothing.
 *
 * Hovering a picture broadcasts its own reference, and a box round the whole
 * picture says nothing. But a row can point at the same region with a box of
 * its own -- one label on the drawing -- and that must light. So only the
 * region itself counts: no cell, no item, no extra places, and no box, or a
 * box that is the whole cut.
 */
export function isOwnHover(
  cut: { region_id?: string; bbox?: number[] },
  hovered: { region_id?: string; bbox?: number[] | null; cell?: unknown; item_id?: string; places?: unknown[] },
): boolean {
  if (hovered.region_id !== cut.region_id || hovered.cell || hovered.item_id) return false;
  if ((hovered.places ?? []).length > 0) return false;
  const b = hovered.bbox;
  if (!b || b.length !== 4) return true;
  const c = cut.bbox ?? [];
  return c.length === 4 && b.every((v, i) => Math.abs(v - c[i]!) < 0.5);
}
