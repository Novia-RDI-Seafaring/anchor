/**
 * sketch.ts  -  reading a drawing as a diagram.
 *
 * A reviewer who draws five shapes, writes a word in each and joins them with
 * lines has described a structure completely. On paper that is a picture; here
 * every shape has a position and every line has two ends that can be matched
 * to shapes, so the same gesture can leave the browser as nodes and edges.
 *
 * This matters more than it sounds. The queue carries what it is given, and
 * what it was given was the five words in the order they were typed -- so a
 * child read as a sibling, and four connectors vanished. An agent woken by
 * that has to guess a shape it was shown precisely.
 *
 * Positions travel too, in flow coordinates, because "put it roughly there"
 * is part of what the drawing said. A diagram rebuilt in the wrong order on
 * the wrong side of the canvas is not the diagram that was drawn.
 */

import {
  insidePolygon,
  isLoop,
  nearRect,
  ringOutline,
  strokeBounds,
  type Box,
  type Point,
  type Rect,
} from "./lasso";

export type SketchNode = {
  /** Stable within one sketch, and referred to by the edges. */
  id: string;
  /** What was written inside the shape, if anything. */
  label: string;
  /** Where it sits, in canvas coordinates. */
  rect: Rect;
  /** An existing canvas element this shape encircles, when it does. */
  encircles?: string;
};

export type SketchEdge = { from: string; to: string };

export type Sketch = { nodes: SketchNode[]; edges: SketchEdge[] };

/** How far outside a shape a line may stop and still count as touching it. */
const TOUCH_PX = 24;

/**
 * Which shape, if any, this point belongs to.
 *
 * Inside the outline, or close enough outside it: a hand aiming at a shape
 * stops a little short as often as a little inside, and a connector that
 * missed by four pixels described the same diagram as one that landed.
 */
function shapeAt(p: Point, shapes: { id: string; outline: Point[]; rect: Rect }[]): string | null {
  for (const s of shapes) {
    if (insidePolygon(p, s.outline) || nearRect(p, s.rect, TOUCH_PX)) return s.id;
  }
  return null;
}

/**
 * Read strokes and words as a diagram.
 *
 * Closed shapes are nodes. Open strokes that begin on one node and end on
 * another are edges -- and only then: a line that starts nowhere, or ends
 * where it began, is a mark the reader made for some other reason, and
 * inventing a relation from it would put something in the agent's hands that
 * nobody drew.
 */
export function resolveSketch(
  strokes: Point[][],
  labels: { text: string; inStroke?: number }[],
  boxes: Box[] = [],
): Sketch {
  const shapes = strokes
    .map((points, index) => ({ points, index }))
    .filter(({ points }) => isLoop(points))
    .map(({ points, index }, n) => {
      const rect = strokeBounds(points);
      const encircled = boxes.find(
        (b) =>
          insidePolygon({ x: b.x + b.width / 2, y: b.y + b.height / 2 }, ringOutline(points)),
      );
      return {
        id: `s${n + 1}`,
        index,
        outline: ringOutline(points),
        rect,
        encircles: encircled?.id,
      };
    });

  const nodes: SketchNode[] = shapes.map((s) => ({
    id: s.id,
    label: labels.find((l) => l.inStroke === s.index)?.text.trim() ?? "",
    rect: s.rect,
    ...(s.encircles ? { encircles: s.encircles } : {}),
  }));

  const edges: SketchEdge[] = [];
  for (const points of strokes) {
    if (isLoop(points) || points.length < 2) continue;
    const from = shapeAt(points[0]!, shapes);
    const to = shapeAt(points[points.length - 1]!, shapes);
    if (!from || !to || from === to) continue;
    if (edges.some((e) => e.from === from && e.to === to)) continue;
    edges.push({ from, to });
  }

  return { nodes, edges };
}

/**
 * The sketch as a sentence, for a reader who only gets text.
 *
 * Every consumer of an intent can read prose; not every one will parse a
 * structure. This says the same thing in the same order so the two can never
 * disagree about what was drawn.
 */
export function describeSketch(sketch: Sketch): string {
  if (sketch.nodes.length === 0) return "";
  const name = (id: string) => {
    const node = sketch.nodes.find((n) => n.id === id);
    return node?.label || node?.encircles || id;
  };
  const parts = [
    sketch.nodes
      .map((n) => `${n.label || "(unlabelled)"} at ${Math.round(n.rect.x)},${Math.round(n.rect.y)}`)
      .join("; "),
  ];
  if (sketch.edges.length > 0) {
    parts.push(sketch.edges.map((e) => `${name(e.from)} -> ${name(e.to)}`).join("; "));
  }
  return parts.join("\n");
}
