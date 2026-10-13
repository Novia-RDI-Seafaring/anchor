/**
 * specLayout.ts — how wide a spec card's columns want to be.
 *
 * The table is fixed-layout, so the card's width decides what shows. With
 * the key column at a flat 45% and the actions column at 5rem, a narrow
 * card had no value column at all, and a card at the usual width clipped a
 * value of sixteen characters. An agent then had to screenshot the card and
 * widen it, a minute per card. The columns now follow the content: the key
 * column takes the share its longest key needs, and a card nobody has sized
 * is as wide as its rows, so values read in full from the start.
 */

export type SpecRowText = { key?: unknown; value?: unknown };

/** The actions column: evidence status over the anchor, in CSS px. */
export const ACTIONS_COL_PX = 80;
/** Horizontal padding of the two text cells together, in CSS px. */
const CELL_PAD_PX = 48;
/** Card border and a little air so the last glyph is not on the edge. */
const EDGE_PX = 16;
/** Average glyph width as a share of the font size, for a UI sans. */
const EM_PER_CHAR = 0.58;

const len = (v: unknown) => (v === null || v === undefined ? 0 : String(v).trim().length);

/** Share of the card's width the key column gets, in percent, 25 to 60. */
export function keyColumnPercent(rows: SpecRowText[]): number {
  const keyChars = Math.max(1, ...rows.map((r) => len(r.key)));
  const valueChars = Math.max(1, ...rows.map((r) => len(r.value)));
  const share = keyChars / (keyChars + valueChars);
  return Math.round(Math.min(0.6, Math.max(0.25, share)) * 100);
}

/**
 * A width at which every key and value of these rows reads in full, in CSS
 * px, between 240 and 760. Above that a card is wider than it is useful, and
 * the cells truncate as they always did.
 */
export function fitWidth(rows: SpecRowText[], fontPx = 14): number {
  const keyChars = Math.max(1, ...rows.map((r) => len(r.key)));
  const valueChars = Math.max(1, ...rows.map((r) => len(r.value)));
  const text = (keyChars + valueChars) * EM_PER_CHAR * fontPx;
  return Math.round(Math.min(760, Math.max(240, text + ACTIONS_COL_PX + CELL_PAD_PX + EDGE_PX)));
}
