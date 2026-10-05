import { type Intent } from "@/api/intents";
import {
  type Point
} from "@/canvas/lasso";
import { type Sketch } from "@/canvas/sketch";
import { type Filed, type Mark, type Note } from "@/stores/markupStore";
import { INK } from "./constants";


/**
 * A filed intent rebuilt from what the server kept of it.
 *
 * After a reload the freehand ink is gone -- it only ever lived in the
 * browser -- but the sketch travelled with the intent, and a sketch is boxes
 * and lines. So the ghost comes back as the boxes that were drawn, with
 * their words in them and the connectors between them, which is the part
 * that mattered.
 */
export function filedFromIntent(intent: Intent): Filed | null {
  const sketch = (intent.payload as { sketch?: Sketch }).sketch;
  const targets = (intent.targets ?? []).map((t) => t.node_id);
  // No drawing to rebuild, but the cards it was about are known: the ghost
  // is the blob round them, which is enough to hang a verdict on. Without
  // this a remark made with a line or a plain ring lost its keep / put it
  // back the moment the page reloaded, and the change it applied stayed
  // unjudged for good.
  if (!sketch || sketch.nodes.length === 0) {
    if (targets.length === 0) return null;
    return {
      intentId: intent.id,
      text: String((intent.payload as { text?: string }).text ?? ""),
      ids: targets,
      sketch: { nodes: [], edges: [] },
      marks: [],
      notes: [],
      color: INK,
      intent,
    };
  }
  // A shape that encircled a card was pointing at the card, which is a
  // target and is wrapped by the blob; drawing its box back as a dotted
  // rectangle put a phantom over the card that read as something planned.
  // Only shapes drawn on open canvas are shapes in their own right.
  const marks: Mark[] = sketch.nodes
    .filter((n) => !n.encircles)
    .map((n) => {
      const r = n.rect;
      return {
        color: INK,
        points: [
          { x: r.x, y: r.y },
          { x: r.x + r.width, y: r.y },
          { x: r.x + r.width, y: r.y + r.height },
          { x: r.x, y: r.y + r.height },
          { x: r.x, y: r.y },
        ],
      };
    });
  const centre = (id: string): Point | null => {
    const n = sketch.nodes.find((x) => x.id === id);
    return n ? { x: n.rect.x + n.rect.width / 2, y: n.rect.y + n.rect.height / 2 } : null;
  };
  for (const e of sketch.edges) {
    const a = centre(e.from);
    const b = centre(e.to);
    if (a && b) marks.push({ color: INK, points: [a, b] });
  }
  const notes: Note[] = sketch.nodes.flatMap((n, i) =>
    n.label
      ? [{ id: `g-${intent.id}-${i}`, x: n.rect.x, y: n.rect.y, text: n.label, inStroke: i, color: INK }]
      : [],
  );
  return {
    intentId: intent.id,
    text: String((intent.payload as { text?: string }).text ?? ""),
    ids: targets,
    sketch,
    marks,
    notes,
    color: INK,
    intent,
  };
}

/** The first line as the title, the rest as the status beneath it. */
export function splitGhostText(text: string): { title: string; status: string } {
  const [title = "", ...rest] = text.split("\n");
  return { title, status: rest.join(" ").trim() };
}
