/**
 * `anchor:` links — how prose points at the page a value came from.
 *
 * A spec row carries its `source_ref` in structured data. Prose has no
 * such slot, so a sentence that quotes a number had no way to say where
 * the number came from. This is that way, written as an ordinary Markdown
 * link:
 *
 *     Rated head is [24 m](anchor:lkh-5?page=3&region=r2) at 8 m³/h.
 *
 * A link, rather than a footnote table or a custom directive, because an
 * agent already knows how to write one, and because the source text stays
 * readable anywhere else it lands.
 *
 * The target maps onto `source_ref` field for field, so a ref written in
 * prose resolves exactly like a ref attached to a spec row — including the
 * selectors that point below a region:
 *
 *     anchor:<slug>?page=3                  the page
 *     anchor:<slug>?page=3&region=r2        one gold region
 *     anchor:<slug>?page=3&item=p3-i0       one silver item inside it
 *     anchor:<slug>?page=3&cell=4,1         one table cell
 *     anchor:<slug>?page=3&bbox=10,20,80,40 an explicit box, last resort
 *
 * Parsing is deliberately strict. A ref that names no document, or no
 * page, is not half-usable: it is broken, and the renderer shows it as
 * broken rather than quietly printing the words as if nothing were meant
 * by them. A pointer an agent got wrong should be visible.
 */
import type { ResolvableRef } from "@/api/documents";

export const ANCHOR_SCHEME = "anchor:";

/** True for any href written in the `anchor:` scheme, valid or not. */
export function isAnchorHref(href: string | undefined | null): boolean {
  return typeof href === "string" && href.trim().toLowerCase().startsWith(ANCHOR_SCHEME);
}

/**
 * Parse an `anchor:` href into a ref. Returns `null` when the href is not
 * an `anchor:` link at all, and `null` for a malformed one — callers that
 * want to tell "not a ref" from "broken ref" ask `isAnchorHref` first.
 */
export function parseAnchorHref(href: string | undefined | null): ResolvableRef | null {
  if (!isAnchorHref(href)) return null;
  const rest = (href as string).trim().slice(ANCHOR_SCHEME.length);
  // `anchor://slug?...` is the shape people write out of habit; accept it.
  const withoutSlashes = rest.startsWith("//") ? rest.slice(2) : rest;
  const [rawSlug, rawQuery] = splitOnce(withoutSlashes, "?");
  const slug = safeDecode(rawSlug).trim();
  if (!slug || slug.includes("/")) return null;

  const params = new URLSearchParams(rawQuery ?? "");
  const page = toPositiveInt(params.get("page"));
  if (page === null) return null;

  const ref: ResolvableRef = { slug, page };
  const region = params.get("region") ?? params.get("region_id");
  if (region) ref.region_id = region;
  const item = params.get("item") ?? params.get("item_id");
  if (item) ref.item_id = item;

  const cell = parseCell(params.get("cell"));
  if (cell) ref.cell = cell;

  const bbox = parseNumberList(params.get("bbox"));
  // A bbox is four numbers or it is not a bbox.
  if (bbox && bbox.length === 4) ref.bbox = bbox;

  return ref;
}

/** The inverse, for anything that writes a ref back into Markdown. */
export function formatAnchorHref(ref: ResolvableRef): string {
  const params = new URLSearchParams();
  if (typeof ref.page === "number") params.set("page", String(ref.page));
  if (ref.region_id) params.set("region", ref.region_id);
  if (ref.item_id) params.set("item", ref.item_id);
  if (typeof ref.cell?.row === "number" && typeof ref.cell?.col === "number") {
    params.set("cell", `${ref.cell.row},${ref.cell.col}`);
  }
  if (ref.bbox?.length === 4) params.set("bbox", ref.bbox.join(","));
  const query = params.toString();
  return `${ANCHOR_SCHEME}${encodeURIComponent(ref.slug ?? "")}${query ? `?${query}` : ""}`;
}

/** A one-line description of where a ref points, for a tooltip. */
export function describeRef(ref: ResolvableRef): string {
  const parts = [ref.slug ?? "", `page ${ref.page}`];
  if (typeof ref.cell?.row === "number" && typeof ref.cell?.col === "number") {
    parts.push(`cell ${ref.cell.row},${ref.cell.col}`);
  } else if (ref.item_id) {
    parts.push(`item ${ref.item_id}`);
  } else if (ref.region_id) {
    parts.push(`region ${ref.region_id}`);
  }
  return parts.filter(Boolean).join(" · ");
}

function splitOnce(value: string, separator: string): [string, string | undefined] {
  const at = value.indexOf(separator);
  if (at === -1) return [value, undefined];
  return [value.slice(0, at), value.slice(at + 1)];
}

function safeDecode(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    // A stray % is not worth throwing over; the raw text is close enough
    // to tell the user which document was meant.
    return value;
  }
}

function toPositiveInt(value: string | null): number | null {
  if (value === null) return null;
  const n = Number(value);
  if (!Number.isInteger(n) || n < 1) return null;
  return n;
}

function parseCell(value: string | null): { row: number; col: number } | null {
  const nums = parseNumberList(value);
  if (!nums || nums.length !== 2) return null;
  const [row, col] = nums;
  if (row === undefined || col === undefined) return null;
  if (!Number.isInteger(row) || !Number.isInteger(col) || row < 0 || col < 0) return null;
  return { row, col };
}

function parseNumberList(value: string | null): number[] | null {
  if (!value) return null;
  const parts = value.split(",").map((p) => Number(p.trim()));
  if (parts.some((n) => !Number.isFinite(n))) return null;
  return parts;
}
