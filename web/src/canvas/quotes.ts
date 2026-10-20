/**
 * Quotes: the words a citation highlights, the way a reader uses a marker.
 *
 * A source ref says where a value comes from; its `quotes` say which words
 * there to light, one or more. Each quote is the printed text (`exact`), with
 * the words around it (`prefix` / `suffix`) when it occurs more than once.
 * The server places a quote when the citation is saved, or when a link is
 * resolved, and gives it `boxes`; the viewer then draws those boxes as they
 * are and searches for nothing. A quote it could not place carries `problem`.
 *
 * In an `anchor:` link a quote is one `quote=` parameter in the browser's
 * text-fragment grammar: `quote=EPDM` or `quote=+140 °C (-,EPDM,-)`.
 */
export type Quote = {
  exact: string;
  prefix?: string;
  suffix?: string;
  page?: number;
  boxes?: number[][];
  problem?: "not_found" | "ambiguous" | "empty";
  candidates?: string[];
  text_here?: string;
};

/** Quotes as written in a ref: placed objects, or `quote=` strings from a link. */
export type RefQuotes = (Quote | string)[] | undefined;

/** The `quote=` text of a quote. */
export function formatQuote(quote: Quote): string {
  let out = quote.exact;
  if (quote.prefix) out = `${quote.prefix}-,${out}`;
  if (quote.suffix) out = `${out},-${quote.suffix}`;
  return out;
}

const isBox = (b: unknown): b is number[] =>
  Array.isArray(b) && b.length === 4 && b.every((v) => typeof v === "number" && Number.isFinite(v));

const placed = (m: Quote | string): m is Quote =>
  typeof m === "object" && m !== null && Array.isArray(m.boxes) && m.boxes.some(isBox);

/** The quotes the server still has to place, as `quote=` parameters. */
export function quoteParams(quotes: RefQuotes): string[] {
  return (quotes ?? [])
    .filter((m) => !placed(m))
    .map((m) => (typeof m === "string" ? m : m && typeof m.exact === "string" ? formatQuote(m) : ""))
    .filter((s) => s.trim() !== "");
}

/** Boxes to draw, per page: the ref's saved quotes and any just placed. */
export function quoteBoxes(
  quotes: RefQuotes,
  page: number,
  resolved?: Quote[] | null,
): { page: number; boxes: number[][] }[] {
  const all = [...(quotes ?? []).filter(placed), ...(resolved ?? []).filter(placed)];
  return all.map((m) => ({ page: m.page ?? page, boxes: (m.boxes ?? []).filter(isBox) }));
}

/** The boxes to draw on one page, in reading order: top to bottom, then left to right. */
export function boxesOnPage(places: { page: number; boxes: number[][] }[], page: number): number[][] {
  return readingOrder(places.filter((p) => p.page === page).flatMap((p) => p.boxes));
}

/** Boxes on one line (their middles within half a line) left to right, lines top down. */
export function readingOrder(boxes: number[][]): number[][] {
  return [...boxes].sort(([ax = 0, ay = 0, , ab = 0], [bx = 0, by = 0, , bb = 0]) => {
    const lineA = (ay + ab) / 2;
    const lineB = (by + bb) / 2;
    const half = Math.min(ab - ay, bb - by) / 2;
    return Math.abs(lineA - lineB) <= half ? ax - bx : lineA - lineB;
  });
}

/** Why some quotes could not be lit, for the viewer's status line. */
export function quoteProblem(resolved?: Quote[] | null): string | null {
  const bad = (resolved ?? []).filter((m) => m.problem);
  if (bad.length === 0) return null;
  const words = bad.map((m) => `“${m.exact}”`).join(", ");
  return bad.some((m) => m.problem === "ambiguous")
    ? `Quoted text occurs more than once here: ${words}.`
    : `Quoted text not found here: ${words}.`;
}
