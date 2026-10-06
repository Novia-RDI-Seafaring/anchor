import { isLoop, type Point, type Rect } from "./strokeGeometry";
import { ringOutline, loopCentre, exitLoop } from "./loopGeometry";

export type Callout = { id: string; centre: Point };
export type CalloutPlace = { x: number; y: number; side: "left" | "right" };

/**
 * Where the words go for highlights drawn on one card: a margin down each
 * side, the way a drawing is called out.
 *
 * Which side is decided by the half of the card the highlight sits in, so the
 * words leave by the nearest edge and the leader never crosses the card. Down
 * each side they are spread evenly over the card's height, keeping the order
 * their highlights are in, so a leader never has to cross another one to
 * reach its own words.
 *
 * Spread, not stacked at their own heights: two highlights on adjacent rows
 * would put their words on top of each other, and nudging them apart one at a
 * time gives a different answer depending on which was drawn first. Dividing
 * the height between them is stable -- the same set of highlights always
 * lands the same way, however they were made -- which is what lets the
 * remaining words re-flow calmly when one is added or taken away.
 */
export function calloutPlaces(
  items: Callout[],
  node: Rect,
  gap: number,
): Map<string, CalloutPlace> {
  const middle = node.x + node.width / 2;
  const places = new Map<string, CalloutPlace>();
  for (const side of ["left", "right"] as const) {
    const mine = items
      .filter((i) => (i.centre.x < middle ? "left" : "right") === side)
      .sort((a, b) => a.centre.y - b.centre.y);
    mine.forEach((item, i) => {
      places.set(item.id, {
        x: side === "left" ? node.x - gap : node.x + node.width + gap,
        // Evenly through the height, inset from both ends rather than
        // starting hard against the top edge.
        y: node.y + ((i + 1) / (mine.length + 1)) * node.height,
        side,
      });
    });
  }
  return places;
}

/**
 * A soft shape around everything one remark covers.
 *
 * A remark is usually several marks and several notes scattered over a
 * card or two, and nothing on screen says which of them belong together --
 * least of all the button that files them, sitting off in a corner with no
 * visible connection to what it is about to send. Drawing one quiet shape
 * around the lot gives that button something to belong to.
 *
 * The outline is the hull pushed outward from the middle, so it clears what
 * it contains rather than cutting corners off it.
 */
export function blobAround(points: Point[], pad: number): Point[] {
  const hull = ringOutline(points);
  if (hull.length < 3) return hull;
  const centre = loopCentre(hull);
  return hull.map((p) => {
    const dx = p.x - centre.x;
    const dy = p.y - centre.y;
    const d = Math.hypot(dx, dy) || 1;
    return { x: p.x + (dx / d) * pad, y: p.y + (dy / d) * pad };
  });
}

/**
 * A closed polygon drawn as a rounded shape.
 *
 * Curves through the midpoint of every edge with the vertex as the control
 * point, which rounds every corner without needing to know where the corners
 * are. A hull is all corners, and a remark is not an angular thing.
 */
export function smoothClosedPath(points: Point[]): string {
  if (points.length < 3) return "";
  const mid = (a: Point, b: Point): Point => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
  const start = mid(points[points.length - 1]!, points[0]!);
  let d = `M ${start.x} ${start.y}`;
  for (let i = 0; i < points.length; i++) {
    const here = points[i]!;
    const next = points[(i + 1) % points.length]!;
    const to = mid(here, next);
    d += ` Q ${here.x} ${here.y} ${to.x} ${to.y}`;
  }
  return `${d} Z`;
}

/**
 * Where to put words so they land on empty canvas.
 *
 * The words sit a short line out from the RIM of what they are about, not a
 * multiple of its size out from its middle. Measured from the middle, a ring
 * round two cards put its words as far away as the ring was wide -- an acre
 * off, on a leader nobody could follow -- while a small ring on one row got
 * them close in. The rim is what the reader sees the line leave, so it is
 * what the gap is measured from, and a big ring gets the same short leader
 * as a small one.
 *
 * Sides are tried first: a label to the left or right of a thing reads as
 * the thing's caption, the way words called out down a card's sides do,
 * while one above or below reads as a heading or a footnote. Then the
 * diagonals, then straight up, and straight down last because that is where
 * the page continues. Each direction is tried close in before further out,
 * so the words stay near what they are about.
 *
 * Everything already on the canvas counts as occupied -- cards, earlier ink,
 * earlier words -- because a remark written on top of another one is worse
 * than a remark written slightly further away.
 */
const COMPASS_DEGREES = [0, 180, -45, -135, 45, 135, -90, 90];

export function clearSpot(
  centre: Point,
  /**
   * How far the rim is from the centre, either one number for something
   * round or a function of the direction (in degrees) for a shape that is
   * not.
   */
  rim: number | ((deg: number) => number),
  /** The leader's length: how far past the rim the words start. */
  gap: number,
  label: { width: number; height: number },
  occupied: Rect[],
  pad: number,
  /**
   * Which way the last remark went, if there was one.
   *
   * Tried at every distance before any other direction is tried at all.
   * Notes on a page line up in a margin: a reader who put the last one out to
   * the right expects the next one out to the right too, and a nearer gap in
   * some other direction is not worth breaking that for. Without this, a
   * sliver of card overlapping the near position was enough to send one
   * remark down while its neighbour went sideways.
   */
  prefer?: number,
): Point {
  const reach = typeof rim === "number" ? () => rim : rim;
  let best: Point | null = null;
  let bestClash = Infinity;
  // Multiples of the leader, so further out still means a line the eye can
  // follow rather than a jump to the next clear acre.
  const steps = [1, 2.5, 4.5, 7];
  const order: [number, number][] = [
    ...(prefer === undefined ? [] : steps.map((st): [number, number] => [st, prefer])),
    ...steps.flatMap((st) => COMPASS_DEGREES.map((d): [number, number] => [st, d])),
  ];
  for (const [step, deg] of order) {
    const r = (deg * Math.PI) / 180;
    const edge = reach(deg);
    const distance = edge + gap * step;
    const at = {
      x: centre.x + Math.cos(r) * distance,
      y: centre.y + Math.sin(r) * distance,
    };
    // The line has to leave the rim on open canvas. A ring round two cards
    // has most of its rim over them, and a leader that set off from inside
    // one read as being about that card, not the ring. So the rim point and
    // the line out from it are checked too, not just where the words land.
    const from = { x: centre.x + Math.cos(r) * edge, y: centre.y + Math.sin(r) * edge };
    const leaderBlocked = [0, 1 / 3, 2 / 3].some((f) => {
      const q = { x: from.x + (at.x - from.x) * f, y: from.y + (at.y - from.y) * f };
      return occupied.some((o) => insideRect(q, o));
    });
    if (leaderBlocked) continue;
    // Where the words will actually sit, which is not centred on this
    // point: they run AWAY from the leader, rightward from it unless the
    // line went left, and they straddle it vertically because the line
    // meets the middle of the text. Judging a centred box instead made
    // every outward direction look half-blocked by whatever the line had
    // just left, and pushed the offer downward into open page.
    const box: Rect = {
      x: Math.cos(r) < 0 ? at.x - label.width : at.x,
      y: at.y - label.height / 2,
      width: label.width,
      height: label.height,
    };
    const clash = occupied.reduce((sum, o) => sum + overlapArea(box, grow(o, pad)), 0);
    if (clash === 0) return at;
    if (clash < bestClash) {
      bestClash = clash;
      best = at;
    }
  }
  // Nowhere is clear: the least cluttered of them, rather than nothing.
  return best ?? { x: centre.x + reach(0) + gap, y: centre.y };
}

/**
 * How far a ring's outline is from its centre in a given direction.
 *
 * A ring drawn by hand is nothing like round: one round two cards side by
 * side is twice as wide as it is tall. Measuring its reach by direction is
 * what lets a leader leave its rim by the same short distance whichever way
 * it goes.
 */
export function rimReach(outline: Point[], centre: Point): (deg: number) => number {
  const span = outline.reduce(
    (m, p) => Math.max(m, Math.hypot(p.x - centre.x, p.y - centre.y)),
    0,
  );
  return (deg) => {
    const r = (deg * Math.PI) / 180;
    // Aim well past the outline: the exit is the last crossing on the way.
    const far = { x: centre.x + Math.cos(r) * span * 4, y: centre.y + Math.sin(r) * span * 4 };
    const exit = exitLoop(outline, centre, far);
    return Math.hypot(exit.x - centre.x, exit.y - centre.y);
  };
}

function insideRect(p: Point, r: Rect): boolean {
  return p.x >= r.x && p.x <= r.x + r.width && p.y >= r.y && p.y <= r.y + r.height;
}

function grow(r: Rect, pad: number): Rect {
  return { x: r.x - pad, y: r.y - pad, width: r.width + pad * 2, height: r.height + pad * 2 };
}

function overlapArea(a: Rect, b: Rect): number {
  const w = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
  const h = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
  return w > 0 && h > 0 ? w * h : 0;
}

/**
 * How text should sit at the end of a leader, so it carries on the line.
 *
 * Words at the end of a line are the line still going: the eye follows the
 * stroke into them without a corner to turn. A horizontal field hanging off a
 * diagonal leader reads as two separate objects that happen to touch.
 *
 * `deg` is the angle to rotate the text by, always within a quarter turn of
 * upright, so it can lean hard but never goes upside down or reads backwards.
 * `flip` says the line ran leftward, so the words extend back from their right
 * edge instead of forward from their left -- which is what keeps them running
 * the same way the line was travelling while still reading left to right.
 */
export function leaderAngle(from: Point, to: Point): { deg: number; flip: boolean } {
  const deg = (Math.atan2(to.y - from.y, to.x - from.x) * 180) / Math.PI;
  // Leftward: turn the text back the right way up and hang it off its far
  // edge. Rotating by the raw angle would stand the words on their head.
  const flip = deg > 90 || deg < -90;
  // Turn back through the nearer half. Always subtracting would send a leader
  // pointing due left (-180) round a full turn instead of levelling it.
  return { deg: flip ? (deg > 0 ? deg - 180 : deg + 180) : deg, flip };
}

/**
 * A leader that lands level, so the words at its end read as a line of text.
 *
 * The last control point shares the label's height: that alone is what makes
 * the curve level as it lands, from the left into words that run right and
 * from the right into words that run left. How it departs is the caller's:
 * a highlight inside a card leaves sideways (`level`), the way a drawing's
 * callouts do; a ring's leader leaves along the line to the words (`chord`),
 * since a rim can be left in any direction.
 */
export function leaderPath(a: Point, b: Point, depart: "level" | "chord" = "chord"): string {
  const left = b.x < a.x;
  const reach = Math.min(90, Math.max(24, Math.abs(b.x - a.x) * 0.6));
  const c1 =
    depart === "level"
      ? { x: a.x + (b.x - a.x) * 0.35, y: a.y }
      : { x: a.x + (b.x - a.x) * 0.35, y: a.y + (b.y - a.y) * 0.35 };
  const c2 = { x: left ? b.x + reach : b.x - reach, y: b.y };
  return `M ${a.x} ${a.y} C ${c1.x} ${c1.y} ${c2.x} ${c2.y} ${b.x} ${b.y}`;
}

/**
 * A stroke pulled at one place, the way a hand pulls on a rubber band.
 *
 * The point nearest the grab moves the whole way; points along the line
 * from it move less, falling off smoothly to nothing at `reach` (measured
 * along the line, and the short way round for a ring). A ring drawn one row
 * short is fixed by pulling its edge over the row, without redrawing it and
 * without any of the shape's forty points being shown or picked.
 */
export function pullStroke(points: Point[], grab: Point, delta: Point, reach: number): Point[] {
  if (points.length < 2 || reach <= 0) return points;
  // Arc position of every point, and the total length.
  const at: number[] = [0];
  for (let i = 1; i < points.length; i++) {
    at.push(at[i - 1]! + Math.hypot(points[i]!.x - points[i - 1]!.x, points[i]!.y - points[i - 1]!.y));
  }
  const total = at[at.length - 1]!;
  if (total === 0) return points;
  let nearest = 0;
  let best = Infinity;
  for (let i = 0; i < points.length; i++) {
    const d = Math.hypot(points[i]!.x - grab.x, points[i]!.y - grab.y);
    if (d < best) {
      best = d;
      nearest = i;
    }
  }
  const ring = isLoop(points);
  const from = at[nearest]!;
  return points.map((p, i) => {
    let d = Math.abs(at[i]! - from);
    if (ring) d = Math.min(d, total - d);
    if (d >= reach) return p;
    const t = 1 - d / reach;
    const w = t * t * (3 - 2 * t);
    return { x: p.x + delta.x * w, y: p.y + delta.y * w };
  });
}

/** Add or remove one id, for correcting a proposal by hand. */
export function toggleId(ids: readonly string[], id: string): string[] {
  return ids.includes(id) ? ids.filter((v) => v !== id) : [...ids, id];
}
