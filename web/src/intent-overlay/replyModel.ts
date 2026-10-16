import { type Ink, type Intent } from "./ports";
import {
  type Point
} from "./lasso";
import { type Sketch } from "./sketch";
import { type Filed, type Mark, type Note } from "./markupStore";
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
  const targets = intent.targetIds ?? [];
  // No drawing to rebuild, but the cards it was about are known: the ghost
  // is the blob round them, which is enough to hang a verdict on. Without
  // this a remark made with a line or a plain ring lost its keep / put it
  // back the moment the page reloaded, and the change it applied stayed
  // unjudged for good.
  // Sent with its ink: drawn back exactly as it was, in its own pen.
  const ink = (intent.payload as { ink?: Ink }).ink;
  if (ink && Array.isArray(ink.marks) && Array.isArray(ink.notes) && (ink.marks.length > 0 || ink.notes.length > 0)) {
    const marks = ink.marks.filter((m) => Array.isArray(m.points) && m.points.length > 0) as Mark[];
    return {
      intentId: intent.id,
      text: String((intent.payload as { text?: string }).text ?? ""),
      ids: targets,
      sketch: sketch ?? { nodes: [], edges: [] },
      marks,
      notes: ink.notes.map((n, i) => ({ ...(n as Note), id: `g-${intent.id}-n${i}` })),
      color: marks[0]?.color ?? INK,
      intent,
    };
  }
  if (!sketch || sketch.nodes.length === 0) {
    const at = (intent.payload as { at?: Point }).at;
    // Words on open canvas: they go back where they were written, so the
    // reply has somewhere to stand after a reload too.
    if (targets.length === 0 && at && Number.isFinite(at.x) && Number.isFinite(at.y)) {
      const text = String((intent.payload as { text?: string }).text ?? "");
      return {
        intentId: intent.id, text, ids: [], sketch: { nodes: [], edges: [] }, marks: [],
        notes: [{ id: `g-${intent.id}-at`, x: at.x, y: at.y, text: text.split("\n\n--- drawn ---")[0] ?? text, color: INK }],
        color: INK, intent,
      };
    }
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
