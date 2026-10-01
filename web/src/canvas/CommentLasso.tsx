import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useReactFlow, useViewport } from "@xyflow/react";

import { Plus, WandSparkles } from "lucide-react";

import { INTENTS_CHANGED_EVENT, intents, type Intent } from "@/api/intents";
import { describeSketch, resolveSketch, type Sketch } from "@/canvas/sketch";
import { describeCuts, resolveCuts, type Cut, type RowBand } from "@/canvas/cuts";
import { describePointers, resolvePointers } from "@/canvas/pointers";
import { describeStrikes, resolveStrikes, type EdgePath, type Strike } from "@/canvas/strikes";
import { previewCentre, previewOps, type Preview } from "@/canvas/preview";
import { useCanvasStore } from "@/stores/canvasStore";
import {
  blobAround,
  calloutPlaces,
  clearSpot,
  leaderPath,
  rimReach,
  clipToBox,
  dropTarget,
  fitStroke,
  rectFrom,
  rectsOverlap,
  ringOutline,
  smoothClosedPath,
  remapPoint,
  remapStroke,
  translateStroke,
  unionRect,
  type Rect,
  insidePolygon,
  insideStroke,
  isLoop,
  lassoHits,
  leaderAngle,
  exitLoop,
  lineOutOfLoop,
  loopAndTail,
  loopCentre,
  markHits,
  MIN_BOX_PX,
  MIN_STROKE_PX,
  nearestOnStroke,
  pullStroke,
  nearRect,
  pivotStroke,
  strokeAt,
  strokeBounds,
  strokeHeading,
  strokeLength,
  toggleId,
  type Box,
  type CalloutPlace,
  type Point,
} from "@/canvas/lasso";

/**
 * CommentLasso — marking up the canvas the way a teacher marks an essay.
 *
 * Ring what is wrong, draw a line to a clear patch, write there. The strokes
 * resolve to node ids before anything leaves the browser, so what reaches an
 * agent is "these three nodes, and this sentence" rather than a polyline. The
 * ink is how the reader said it; the ids are what they said it about.
 *
 * The gestures, and why each is shaped this way:
 *
 * A stroke proposes a selection live, so the reader watches a line become a
 * ring rather than finding out when they let go. Rings always select; the
 * FIRST stroke selects whatever its shape. Every other line is just ink, so a
 * connector drawn to a clear patch does not sweep up whatever it crossed.
 *
 * The proposal is meant to be corrected: cmd-click adds or removes a node.
 * Generous-then-fix beats precise-then-fail, because a near miss that caught
 * one node too many costs a click, while one that caught nothing leaves the
 * reader wondering what they did wrong.
 *
 * After a ring catches something, a leader and a cursor are OFFERED at the end
 * of it. A reviewer who has just drawn round a value is about to say why, and
 * making them find a spot and double-click first is a gesture for the tool's
 * benefit rather than theirs. The offer costs nothing when it is wrong:
 * starting anything else withdraws it.
 *
 * Marks queue rather than sending one at a time, because sending each one as
 * it is written would wake the agent once per thought. Queued ink stays on the
 * board, faded: what you have already said should be visible while you decide
 * what to say next.
 *
 * The selection is INERT throughout. It cannot drag, delete or rewire
 * anything, which is what makes it safe to scribble across a board you care
 * about — and is the real argument for a mode rather than a chord, alongside
 * the fact that a middle-drag does not exist on a trackpad.
 */

const NOTE_W = 320;
const NOTE_H = 110;
const NOTE_FONT_PX = 26;
/**
 * How far inside a drawn shape its words sit, in flow units.
 *
 * A hand-drawn border is ragged, and text run right up to it collides with the
 * wobble on one line and leaves a gap on the next.
 */
const HOST_INSET_PX = 10;
/** A resize handle's square, in screen pixels: small, but aimable. */
const HANDLE_PX = 13;
/**
 * How near a card a line has to stop before it counts as joined to it.
 *
 * A few pixels either side of the edge, because a hand aiming at something
 * stops just short about as often as it stops just inside.
 */
const SNAP_PX = 10;
/** How far a called-out label stands off the card it belongs to. */
const CALLOUT_GAP_PX = 40;
/** About a centimetre in from the corner the queue panel rests in. */
const PANEL_INSET_PX = 40;
/** The region behind a remark: a quiet slate, whichever pens were used. */
const BLOB_FILL = "#4b4f63";
/** The grounds sent remarks rest on, one each in turn: quiet, and unlike any pen. */
const GHOST_GROUNDS: readonly [string, ...string[]] = [
  "#8a93a6",
  "#c9a86a",
  "#6fa8a0",
  "#b58aa5",
  "#8f9c6b",
  "#a68a7a",
];
/** How far the shape around a remark stands off what it contains. */
const BLOB_PAD_PX = 46;
/** Clear air between where a leader stops and where its words start. */
const NOTE_LEAD_GAP_PX = 10;
/** The move tab: wide enough to read as a pull, small enough to stay out of it. */
const CORNERS = [
  { x: 0, y: 0 },
  { x: 1, y: 0 },
  { x: 1, y: 1 },
  { x: 0, y: 1 },
] as const;
/** The erase button's box. Thumb-sized, so it can be hit without aiming. */
const ERASE_PX = 26;
const INK = "rgb(139, 92, 246)";

/**
 * The pens on the bar, in the order the number keys reach them.
 *
 * Nine, because that is how many number keys there are to hand and how many
 * distinct colours a reader can actually keep meanings for. Violet first: it
 * is the colour every mark has been until now, so the default does not move.
 */
const PALETTE = [
  { key: "1", name: "violet", ink: "rgb(139, 92, 246)" },
  { key: "2", name: "red", ink: "rgb(220, 38, 38)" },
  { key: "3", name: "orange", ink: "rgb(234, 88, 12)" },
  { key: "4", name: "amber", ink: "rgb(202, 138, 4)" },
  { key: "5", name: "green", ink: "rgb(22, 163, 74)" },
  { key: "6", name: "teal", ink: "rgb(13, 148, 136)" },
  { key: "7", name: "blue", ink: "rgb(37, 99, 235)" },
  { key: "8", name: "pink", ink: "rgb(219, 39, 119)" },
  { key: "9", name: "graphite", ink: "rgb(63, 63, 70)" },
] as const;


/** The square a mark is sized by, drawn with the same pen as the mark. */
function SketchSquare() {
  return (
    <svg viewBox="0 0 14 14" width={HANDLE_PX} height={HANDLE_PX} aria-hidden>
      <path
        d="M2.2 2.6 L11.4 1.9 L11.8 11.5 L2.5 11.9 Z"
        fill="white"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * The × that removes a stroke, drawn rather than typed.
 *
 * Everything else on this layer is hand-drawn: fat round-capped strokes in
 * violet, a ring that never quite closes. A crisp grey × in a bordered
 * circle belongs to the application's chrome, and next to the ink it reads as
 * part of the page rather than part of the mark-up. So this is two pen
 * strokes and a ring, off-true on purpose, in the same colour and weight as
 * whatever it is offering to erase.
 */
function SketchCross() {
  return (
    <svg viewBox="0 0 24 24" width={ERASE_PX} height={ERASE_PX} aria-hidden>
      {/* A pale disc, so the glyph stays legible where it sits on the ink. */}
      <circle cx="12" cy="12" r="10" fill="rgba(255,255,255,0.82)" />
      {/* Drawn round, not stamped: the ends overrun the way a pen does. */}
      <path
        d="M3.4 11.2 C2.6 5.8 6.6 2.2 12.3 2.1 C17.8 2 21.6 5.6 21.5 11.4 C21.4 17.4 17.3 21.4 11.7 21.3 C6.2 21.2 2.5 17.3 3.1 11.9"
        fill="none"
        stroke={INK}
        strokeWidth={1.7}
        strokeOpacity={0.55}
        strokeLinecap="round"
      />
      <path d="M8.2 8.6 L15.9 15.7" fill="none" stroke="currentColor" strokeWidth={2.6} strokeLinecap="round" />
      <path d="M16 8.4 L8.4 15.9" fill="none" stroke="currentColor" strokeWidth={2.6} strokeLinecap="round" />
    </svg>
  );
}

/**
 * Keys that end a note, shared by both kinds.
 *
 * Enter means "that is what I wanted to say"; Shift+Enter makes a new row,
 * because a remark is often two. Writing is a mode, and without a way out of
 * it the reader stays caught in the box they were typing in -- handles up,
 * pointer events claimed -- when what they want next is to draw a line from
 * it to somewhere else.
 *
 * Escape leaves the field too, and keeps the words. It used to throw them
 * away, which is what escape does to a dialog, but nobody types a sentence
 * and then reaches for escape meaning "and forget that". Empty notes are
 * dropped on the way out either way. Neither key reaches the canvas: the
 * mode's own escape clears the whole mark, and the field's must not.
 */
function noteKeys({ onCommit }: { onCommit: () => void }) {
  return (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    e.stopPropagation();
    if ((e.key === "Enter" && !e.shiftKey) || e.key === "Escape") {
      e.preventDefault();
      onCommit();
      e.currentTarget.blur();
    }
  };
}

/**
 * Take the caret when this note becomes the one being written in, and select
 * what is already there.
 *
 * `autoFocus` only fires when the element mounts, and a note that is picked
 * back up was already on screen.
 *
 * Selecting matters because of how these get reopened: a double-click on the
 * words is nearly always "this one is wrong, let me say it again", and
 * leaving the caret parked mid-word meant clearing the old text by hand
 * first. An empty note selects nothing, so a fresh one is unaffected.
 */
function useCaret(ref: React.RefObject<HTMLTextAreaElement | null>, editing: boolean) {
  useEffect(() => {
    if (!editing) return;
    const el = ref.current;
    if (!el) return;
    el.focus();
    el.select();
  }, [ref, editing]);
}

/**
 * Text written inside a shape that was drawn.
 *
 * Centred both ways, because the box IS the note: the words belong in the
 * middle of it the way a label belongs in the middle of a box, not tucked
 * into a corner where they read as the start of a paragraph.
 *
 * A textarea cannot centre its own content vertically, so the padding is
 * measured: strip it, read how tall the text actually is, and put half the
 * slack back on top. When the text outgrows the shape the box grows downward
 * rather than clipping — at that point the reader has stopped drawing a
 * shape and started writing in a box, and losing the end of a sentence to a
 * border they sketched by hand would be a poor trade.
 */
function HostedNote({
  value, offered, left, top, width, height, fontSize, editing, color,
  onChange, onBlur, onGrow, onCommit,
}: {
  value: string;
  /** Opened by the shape being drawn rather than asked for, and still empty. */
  offered: boolean;
  left: number;
  top: number;
  width: number;
  height: number;
  fontSize: number;
  /** Is this the note being written in right now? */
  editing: boolean;
  /** The pen it was written with. */
  color: string;
  onChange: (v: string) => void;
  onBlur: () => void;
  /** The words no longer fit: the shape needs to be this tall, in pixels. */
  onGrow: (neededPx: number) => void;
  /** Done writing: let go of the field so the next stroke lands on canvas. */
  onCommit: () => void;
}) {
  const ref = useRef<HTMLTextAreaElement | null>(null);
  useCaret(ref, editing);
  // Held in a ref so re-measuring is driven by the text and the box, not by
  // the parent handing down a new closure on every render.
  const grow = useRef(onGrow);
  grow.current = onGrow;

  // Measured and applied in one pass, imperatively.
  //
  // Doing half of it through state did not work: the effect zeroes the padding
  // to measure, and when the newly computed padding equals what state already
  // held, React skips the re-render that would have put it back -- leaving the
  // measurement's own zero on screen. So the final values are written here
  // rather than handed to React to re-apply.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.paddingTop = "0px";
    el.style.height = "auto";
    const text = el.scrollHeight;
    const box = Math.max(height, text);
    el.style.height = `${box}px`;
    el.style.paddingTop = `${Math.max(0, (box - text) / 2)}px`;
    // The shape itself has to follow. Growing only the textarea left the words
    // hanging out of the bottom of a box that stayed the size it was drawn.
    // One pixel of slack keeps a rounding difference from asking forever.
    if (text > height + 1) grow.current(text);
  }, [value, height, width, fontSize]);

  return (
    <textarea
      ref={ref}
      data-testid="comment-lasso-note"
      data-offered={offered ? "" : undefined}
      // One row, so `height: auto` measures the WORDS. A textarea with no
      // row count falls back to two of them, which made one short line
      // measure as tall as two -- and the padding that centres it came out
      // half a line short, sitting the text above the middle of the shape.
      rows={1}
      value={value}
      placeholder={offered ? "write…" : "write"}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onBlur}
      onKeyDown={noteKeys({ onCommit })}
      onPointerDown={(e) => e.stopPropagation()}
      onDoubleClick={(e) => e.stopPropagation()}
      className="absolute z-40 resize-none overflow-hidden border-0 bg-transparent px-1 text-center leading-tight outline-none placeholder:opacity-40"
      style={{
        color,
        left,
        top,
        width,
        // Never takes the pointer, not even while it is being written in.
        //
        // Words inside a drawn box are a label on the box, and the box is
        // something to draw out of. A field that claimed its own area made
        // the middle of the shape -- where a line out of it naturally starts
        // -- a place where drawing silently did nothing, and the only way out
        // was to click away first and come back. The caret arrives by itself
        // and the keyboard reaches it; a double-click picks the words back up.
        pointerEvents: "none",
        fontFamily: '"Marker Felt", "Bradley Hand", "Segoe Print", "Comic Sans MS", cursive',
        fontSize,
      }}
    />
  );
}

/**
 * One line to say something back, under a card that asked for a verdict.
 *
 * Keep and put it back are the verdict; this is the rest of the sentence:
 * "put it back, I meant every other row". Without it the reader had to go
 * to the panel, find the thread, and write there -- a detour that mostly
 * ended in not saying it. Enter sends; the line clears and stays.
 */
function ReplyLine({ color, onSend }: { color: string; onSend: (text: string) => void }) {
  const [text, setText] = useState("");
  const send = () => {
    const t = text.trim();
    if (!t) return;
    onSend(t);
    setText("");
  };
  return (
    <div className="mt-1.5 flex gap-1">
      <input
        data-testid="comment-lasso-reply"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === "Enter") send();
        }}
        placeholder="reply…"
        className="min-w-0 flex-1 rounded border border-neutral-300 px-1.5 py-0.5 text-[11px] outline-none focus:border-neutral-500"
      />
      <button
        type="button"
        className="rounded px-2 py-0.5 text-[11px] text-white"
        style={{ background: color }}
        onClick={send}
      >
        send
      </button>
    </div>
  );
}

/**
 * A comment written on open canvas, at the end of a leader or where it was
 * asked for. No box and no border: felt pen on the page, rather than another
 * card someone added to the design.
 */
function FloatingNote({
  value, offered, editing, at, width, deg, flip, gap, fontSize, color,
  onChange, onBlur, onCommit, onGrab, onDrag, onDrop, onEdit, onRemove,
  active,
}: {
  value: string;
  /** Suggested rather than asked for, and not yet taken up. */
  offered: boolean;
  editing: boolean;
  /** Where the leader ends: the words are centred on this point. */
  at: { x: number; y: number };
  width: number;
  /** The leader's lean, turned the right way up. */
  deg: number;
  /** The leader ran leftward, so the words hang back off their right edge. */
  flip: boolean;
  /** Clear air between the end of the line and the first letter. */
  gap: number;
  /** The pen it was written with. */
  color: string;
  fontSize: number;
  onChange: (v: string) => void;
  onBlur: () => void;
  onCommit: () => void;
  /** Picked up by its words, to be carried somewhere else. */
  onGrab: (e: React.PointerEvent) => void;
  onDrag: (e: React.PointerEvent) => void;
  onDrop: (e: React.PointerEvent) => void;
  /** Double-click: the words become a field again. */
  onEdit: () => void;
  /** Picked out: clicked or dragged, so its cross is showing. */
  active: boolean;
  /** Take the label and the line it belongs to, which are one thing. */
  onRemove: () => void;
}) {
  const ref = useRef<HTMLTextAreaElement | null>(null);
  const mirror = useRef<HTMLSpanElement | null>(null);
  const [textWidth, setTextWidth] = useState(0);
  useCaret(ref, editing);
  // Carrying the words while writing in them. The press is left to the
  // browser, which is what puts the caret where it was clicked; what the
  // hand does next decides. Sideways is selecting text, which the browser
  // is already doing. Up or down is picking the words up, and once picked
  // up they stay picked up until let go, however the hand wanders. Waiting
  // to click away and then come back for the words was the case that made
  // this: the caret is in them and the reader wants them somewhere else.
  const press = useRef<{ x: number; y: number; mode: "undecided" | "move" | "select" } | null>(null);
  const [moving, setMoving] = useState(false);
  // Where on a line the pointer is: over the middle of the letters it is a
  // caret, near the top or bottom edge of the line it is a hand.
  const [zone, setZone] = useState<"text" | "grab">("text");
  const zoneAt = (e: React.PointerEvent<HTMLTextAreaElement>) => {
    const lineHeight = fontSize * 1.25;
    const local = e.nativeEvent.offsetY - 4;
    const frac = (((local % lineHeight) + lineHeight) % lineHeight) / lineHeight;
    return frac < 0.22 || frac > 0.78 ? "grab" : "text";
  };
  // How wide the words actually are, which a textarea will not say: it is
  // always the width it was given. A hidden span in the same face and size is
  // measured instead, so the cross can sit just past the last character
  // rather than out at the edge of a field that is mostly empty.
  useLayoutEffect(() => {
    setTextWidth(mirror.current?.offsetWidth ?? 0);
  }, [value, fontSize]);
  // Grow with the lines rather than scroll inside a fixed box. The wrapper
  // does the centring, so growth pushes both ways off the leader's end and
  // the line keeps meeting the middle of the text however much is written.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [value, width, fontSize]);

  return (
    <div
      data-testid="comment-lasso-note-frame"
      className="absolute z-40"
      style={{
        // A point, not a box: the wrapper has no size, so rotating it turns
        // the text about exactly where the leader ends.
        left: at.x,
        top: at.y,
        transformOrigin: "0 0",
        transform: `rotate(${deg}deg)`,
      }}
    >
      {/* A frame the height of the words, centred on the leader's end. The
          cross hangs off its corner, so it follows the text however the line
          leans and however many lines are written. */}
      <div
        style={{
          position: "absolute",
          left: flip ? -width - gap : gap,
          top: 0,
          width,
          transform: "translateY(-50%)",
        }}
      >
      {/* Measured, not shown. The longest line decides, so the cross clears
          the widest of them rather than landing in the middle of one. */}
      <span
        ref={mirror}
        aria-hidden
        style={{
          position: "absolute",
          visibility: "hidden",
          whiteSpace: "pre",
          left: 0,
          top: 0,
          fontFamily: '"Marker Felt", "Bradley Hand", "Segoe Print", "Comic Sans MS", cursive',
          fontSize,
        }}
      >
        {value.split("\n").reduce((a, b) => (b.length > a.length ? b : a), "")}
      </span>
      {active && value.trim() ? (
        <button
          type="button"
          data-testid="comment-lasso-erase-label"
          aria-label="Delete this label and its line"
          title="Delete"
          onPointerDown={(e) => {
            e.stopPropagation();
            e.preventDefault();
          }}
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          style={{
            position: "absolute",
            top: -ERASE_PX * 0.55,
            // Just past the last character, on the far side from where the
            // words grow: the text hangs off its right edge when the line ran
            // leftward, so the cross goes to the left of it.
            left: flip
              ? width - Math.min(width, textWidth) - ERASE_PX * 0.45
              : Math.min(width, textWidth) - ERASE_PX * 0.55,
            width: ERASE_PX,
            height: ERASE_PX,
            display: "grid",
            placeItems: "center",
            color,
            cursor: "pointer",
          }}
        >
          <SketchCross />
        </button>
      ) : null}
      <textarea
        ref={ref}
        data-testid="comment-lasso-note"
        data-offered={offered ? "" : undefined}
        data-flip={flip ? "" : undefined}
        rows={1}
        value={value}
        placeholder={offered ? "write…" : "write"}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        onKeyDown={noteKeys({ onCommit })}
        // Written, and not being written in: the words are a thing to pick up
        // and carry. preventDefault keeps a grab from putting a caret in them
        // -- moving a label and editing it are different gestures, and the
        // second one is a double-click.
        onPointerDown={(e) => {
          e.stopPropagation();
          if (!editing) {
            e.preventDefault();
            onGrab(e);
            return;
          }
          // Not prevented: the browser places the caret, or starts a
          // selection. Pressing in the hand zone picks up at once.
          if (zoneAt(e) === "grab") {
            e.preventDefault();
            press.current = { x: e.clientX, y: e.clientY, mode: "move" };
            setMoving(true);
            onGrab(e);
            return;
          }
          press.current = { x: e.clientX, y: e.clientY, mode: "undecided" };
        }}
        onPointerMove={(e) => {
          if (!editing) {
            onDrag(e);
            return;
          }
          const pr = press.current;
          if (!pr) {
            const z = zoneAt(e);
            setZone((prev) => (prev === z ? prev : z));
            return;
          }
          if (pr.mode === "undecided") {
            const dx = e.clientX - pr.x;
            const dy = e.clientY - pr.y;
            if (Math.hypot(dx, dy) < 4) return;
            pr.mode = Math.abs(dy) > Math.abs(dx) ? "move" : "select";
            if (pr.mode === "move") {
              setMoving(true);
              onGrab(e);
            }
            return;
          }
          if (pr.mode === "move") onDrag(e);
        }}
        onPointerUp={(e) => {
          if (!editing) {
            onDrop(e);
            return;
          }
          if (press.current?.mode === "move") {
            onDrop(e);
            setMoving(false);
            // The selection the press began is not what was meant.
            const el = ref.current;
            if (el) el.setSelectionRange(el.selectionStart, el.selectionStart);
          }
          press.current = null;
        }}
        onPointerCancel={(e) => {
          if (!editing) {
            onDrop(e);
            return;
          }
          if (press.current?.mode === "move") {
            onDrop(e);
            setMoving(false);
          }
          press.current = null;
        }}
        onDoubleClick={(e) => {
          e.stopPropagation();
          if (!editing) onEdit();
        }}
        className="absolute resize-none overflow-hidden border-0 bg-transparent px-0 py-1 leading-tight outline-none placeholder:opacity-40"
        style={{
          color,
          // A caret while writing, a hand the rest of the time.
          cursor: !editing ? "grab" : moving ? "grabbing" : zone,
          position: "relative",
          width: "100%",
          textAlign: flip ? "right" : "left",
          // While the words are being carried the browser must not go on
          // extending the selection the press began.
          userSelect: moving ? "none" : undefined,
          // An empty offer claims nothing -- there is nothing in it to point
          // at, and the caret reaches it without the pointer's help. Once
          // there are words they are a label: grabbable, so it can be carried
          // to where it reads better, with its leader following.
          pointerEvents: value.trim() ? "auto" : "none",
          // Marker Felt ships with macOS; the rest are the nearest thing
          // elsewhere, ending at whatever the system calls cursive.
          fontFamily: '"Marker Felt", "Bradley Hand", "Segoe Print", "Comic Sans MS", cursive',
          fontSize,
        }}
      />
      </div>
    </div>
  );
}

/**
 * Roughly where a comment written on open canvas sits.
 *
 * Its anchor is the first line of text, and the words run down and away from
 * there; which way depends on the leader that brought them. Approximate on
 * purpose -- this decides which note the reader meant, not where a pixel goes.
 */
function noteRect(n: Note): Rect {
  return {
    x: n.x - NOTE_W / 2,
    y: n.y - NOTE_FONT_PX,
    width: NOTE_W * 1.5,
    height: NOTE_H + NOTE_FONT_PX,
  };
}

/**
 * Everything on the mark-up layer the rubber band touches.
 *
 * Touch, not contain: a band that has to swallow a mark whole punishes the
 * reader for a short drag over a long stroke, and the selection is meant to be
 * corrected anyway.
 */
function withinBand(band: Rect, strokes: Point[][], notes: Note[]): Selection {
  return {
    strokes: strokes
      .map((st, i) => [i, strokeBounds(st)] as const)
      .filter(([, b]) => rectsOverlap(band, b))
      .map(([i]) => i),
    notes: notes
      .filter((n) => n.inStroke === undefined && rectsOverlap(band, noteRect(n)))
      .map((n) => n.id),
  };
}

/** Is this point on a comment written on open canvas? */
function hitsNote(p: Point, n: Note): boolean {
  if (n.inStroke !== undefined) return false;
  const r = noteRect(n);
  return p.x >= r.x && p.x <= r.x + r.width && p.y >= r.y && p.y <= r.y + r.height;
}

/**
 * A queued remark's words, as ink rather than as a field.
 *
 * Already said, so it is faint and cannot be typed in -- but it is still
 * there. Fading the strokes and dropping the text left the pile as a set of
 * anonymous scribbles, and a mark with no words says nothing about why it was
 * drawn, which is the whole content of the remark.
 */
function FaintNote({
  note, strokes, screen, zoom,
}: {
  note: Note;
  strokes: Point[][];
  screen: (p: Point) => Point;
  zoom: number;
}) {
  const shared = {
    fontFamily: '"Marker Felt", "Bradley Hand", "Segoe Print", "Comic Sans MS", cursive',
    fontSize: NOTE_FONT_PX * zoom,
    opacity: 0.35,
    color: note.color ?? INK,
    whiteSpace: "pre-wrap" as const,
  };
  const host = note.inStroke !== undefined ? strokes[note.inStroke] : undefined;
  if (host) {
    const b = strokeBounds(host);
    const inset = Math.min(HOST_INSET_PX, b.width / 6);
    const at = screen({ x: b.x + inset, y: b.y + inset });
    return (
      <div
        data-testid="comment-lasso-queued-note"
        className="pointer-events-none absolute z-30 text-center leading-tight"
        style={{
          ...shared,
          left: at.x,
          top: at.y,
          width: Math.max(20, (b.width - inset * 2) * zoom),
          height: Math.max(20, (b.height - inset * 2) * zoom),
          display: "grid",
          placeItems: "center",
        }}
      >
        {note.text}
      </div>
    );
  }
  const at = screen({ x: note.x, y: note.y });
  // Level unless the words carry on a line the reader drew; an offered
  // leader lands level, so its words sit level too.
  const lean =
    note.from && note.continues
      ? leaderAngle(note.from, note)
      : { deg: 0, flip: Boolean(note.from) && note.x < note.from!.x };
  const width = NOTE_W * zoom;
  return (
    <div
      className="pointer-events-none absolute z-30"
      style={{ left: at.x, top: at.y, transformOrigin: "0 0", transform: `rotate(${lean.deg}deg)` }}
    >
      <div
        data-testid="comment-lasso-queued-note"
        className="absolute leading-tight"
        style={{
          ...shared,
          left: lean.flip ? -width - NOTE_LEAD_GAP_PX * zoom : NOTE_LEAD_GAP_PX * zoom,
          top: 0,
          transform: "translateY(-50%)",
          width,
          textAlign: lean.flip ? "right" : "left",
        }}
      >
        {note.text}
      </div>
    </div>
  );
}

type Note = {
  id: string;
  x: number;
  y: number;
  text: string;
  /** Written inside a shape that was drawn: the note takes that shape's box. */
  inStroke?: number;
  /** Where the leader that offered this note started. */
  from?: Point;
  /**
   * The words carry on a stroke the reader drew, rather than a leader offered
   * to them, so no separate line is drawn to reach them.
   */
  continues?: boolean;
  /** Which stroke they carry on from, so dragging them can swing it. */
  onStroke?: number;
  /**
   * Which ring they belong to. The line is not stored: it is drawn from that
   * ring's centre to wherever the words are now, clipped at the outline. So
   * carrying the words anywhere keeps the line looking like it comes out of
   * the middle of the ring, with no pivot point left behind on the edge.
   */
  ringStroke?: number;
  /** Offered rather than asked for: it evaporates unless it is used. */
  offered?: boolean;
  /** The pen it was written with. */
  color?: string;
  /**
   * Carried by hand, so the layout leaves it alone.
   *
   * Auto-placed words are positioned by rule, not stored; dragging one is the
   * reader saying they want it exactly there, and a rule that immediately put
   * it back would be arguing with them.
   */
  pinned?: boolean;
};

type Queued = {
  id: string;
  text: string;
  ids: string[];
  /** The drawing read as nodes and edges, so the agent gets the shape of it. */
  sketch: Sketch;
  /** Lines across tables, read as the row boundary they went through. */
  cuts: Cut[];
  /** Crosses over edges, read as the edge to take away. */
  strikes: Strike[];
  marks: Mark[];
  /** The words as written and placed, so a queued remark still reads as one. */
  notes: Note[];
};

/**
 * One drawn stroke and the pen it was drawn with.
 *
 * Strokes used to be bare geometry, which left nowhere to put a colour. The
 * points stay separate from the colour rather than being mixed into it, so
 * every geometry helper keeps taking plain points and none of them had to
 * learn about pens.
 */
type Mark = {
  points: Point[];
  color: string;
  /**
   * Drawn from one element and dropped on another: a join rather than a
   * remark. The ids are what an agent reads -- "connect these two" -- and the
   * line is clipped to the edge so it looks joined rather than drawn over.
   */
  link?: { from: string | null; to: string };
};

/**
 * A remark that has been sent, still on the board as a ghost.
 *
 * Filing an intent used to make it vanish, which left the reader looking at
 * a blank canvas and a line of text saying it had gone somewhere. It has not
 * gone anywhere: the agent is about to work on exactly this spot. So the ink
 * stays, faint, and becomes the place where that work shows up -- the
 * agent's progress, its questions, and in the end the proposal to approve.
 */
type Filed = {
  intentId: string;
  text: string;
  ids: string[];
  sketch: Sketch;
  marks: Mark[];
  notes: Note[];
  /** The pen it was drawn with: the ghost and its status wear the same one. */
  color: string;
  /** The ground it rested on while it was being drawn; the ghost keeps it. */
  ground?: string;
  /** The thread as last fetched. Null until the first poll lands. */
  intent: Intent | null;
};

/**
 * A remark set aside, unsent, while another is being drawn.
 *
 * Several asks can be in the making at once -- one half-drawn while a
 * second comes to mind -- and they must not fold into each other. Each
 * rests on its own ground; a tap on that ground brings it back to the pen.
 */
type Stack = Queued & { ground: string };

/** Size of a ghost node the agent placed without saying how big. */
const GHOST_W = 220;
const GHOST_H = 90;
/** How often the board asks after its filed remarks, while it has any. */
const THREAD_POLL_MS = 2500;

/**
 * A filed intent rebuilt from what the server kept of it.
 *
 * After a reload the freehand ink is gone -- it only ever lived in the
 * browser -- but the sketch travelled with the intent, and a sketch is boxes
 * and lines. So the ghost comes back as the boxes that were drawn, with
 * their words in them and the connectors between them, which is the part
 * that mattered.
 */
function filedFromIntent(intent: Intent): Filed | null {
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

/**
 * All four corners of a box. Two opposite corners are enough to describe a
 * rectangle but not to bound one: a hull given only those can run straight
 * across the other two, which cut the corner off the very card a remark was
 * about.
 */
function rectCorners(r: Rect): Point[] {
  return [
    { x: r.x, y: r.y },
    { x: r.x + r.width, y: r.y },
    { x: r.x + r.width, y: r.y + r.height },
    { x: r.x, y: r.y + r.height },
  ];
}

/** The first line as the title, the rest as the status beneath it. */
function splitGhostText(text: string): { title: string; status: string } {
  const [title = "", ...rest] = text.split("\n");
  return { title, status: rest.join(" ").trim() };
}

/** Marks the reader has picked out: drawn strokes, and comments on open canvas. */
type Selection = { strokes: number[]; notes: string[] };
const NOTHING_SELECTED: Selection = { strokes: [], notes: [] };

export function CommentLasso({
  active,
  boxes,
  workspaceSlug,
  onFiled,
  onExit,
}: {
  active: boolean;
  /** Every node's box, in flow coordinates. */
  boxes: Box[];
  /** The canvas the remark is about. */
  workspaceSlug: string;
  /** Called once remarks have been filed. */
  onFiled?: () => void;
  /** Put the pen down: escape with nothing left to clear leaves the mode. */
  onExit?: () => void;
}) {
  const { screenToFlowPosition, getViewport, setViewport } = useReactFlow();
  const storeNodes = useCanvasStore((st) => st.nodes);
  const storeEdges = useCanvasStore((st) => st.edges);
  const storeEdgesRef = useRef(storeEdges);
  storeEdgesRef.current = storeEdges;
  const storeNodesRef = useRef(storeNodes);
  storeNodesRef.current = storeNodes;

  /**
   * Where a card's rows sit, in canvas coordinates.
   *
   * The rendered table is the only thing that knows this -- row heights come
   * from wrapped text and fonts, not from data -- so the rows are read off
   * the DOM in order and zipped with the store's row keys. Null for a card
   * that has no rows to cut between.
   */
  const rowsOf = useCallback(
    (nodeId: string): RowBand[] | null => {
      const rows = (storeNodesRef.current[nodeId]?.data as { rows?: { key?: string }[] } | undefined)
        ?.rows;
      if (!rows || rows.length < 2) return null;
      // Node ids are plain slugs, but escape when the platform can: jsdom may not.
      const safe = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(nodeId) : nodeId;
      const el = document.querySelector(`.react-flow__node[data-id="${safe}"]`);
      if (!el) return null;
      const trs = Array.from(el.querySelectorAll("tr[data-row-handle-id]"));
      if (trs.length !== rows.length) return null;
      return trs.map((tr, i) => {
        const r = tr.getBoundingClientRect();
        const top = screenToFlowPosition({ x: r.left, y: r.top });
        const bottom = screenToFlowPosition({ x: r.left, y: r.bottom });
        return { key: String(rows[i]?.key ?? i + 1), top: top.y, bottom: bottom.y };
      });
    },
    [screenToFlowPosition],
  );
  /**
   * Every edge as it is drawn right now, sampled along its path.
   *
   * Read from the DOM for the same reason rows are: the browser is the only
   * place that knows where a routed curve actually runs, and a cross drawn
   * over it has to be matched against that, not against its endpoints.
   */
  const edgesOf = useCallback((): EdgePath[] => {
    const out: EdgePath[] = [];
    for (const [id, edge] of Object.entries(storeEdgesRef.current)) {
      const safe = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(id) : id;
      const el = document.querySelector<SVGPathElement>(
        `.react-flow__edge[data-id="${safe}"] path.react-flow__edge-path`,
      );
      if (!el || typeof el.getTotalLength !== "function") continue;
      const total = el.getTotalLength();
      if (!Number.isFinite(total) || total <= 0) continue;
      const svg = el.ownerSVGElement;
      const ctm = el.getScreenCTM();
      if (!svg || !ctm) continue;
      const points: Point[] = [];
      const step = Math.max(8, total / 64);
      for (let d = 0; d <= total; d += step) {
        const at = el.getPointAtLength(d).matrixTransform(ctm);
        points.push(screenToFlowPosition({ x: at.x, y: at.y }));
      }
      out.push({ id, source: edge.source, target: edge.target, points });
    }
    return out;
  }, [screenToFlowPosition]);
  // Subscribed, not read on demand. Nothing re-rendered this overlay when the
  // canvas panned or zoomed, so the ink kept the screen coordinates it had
  // when it was drawn and slid out of register with the cards underneath.
  const viewport = useViewport();

  const [marks, setMarks] = useState<Mark[]>([]);
  /** The pen in hand. Number keys pick it; everything drawn next takes it. */
  const [ink, setInk] = useState<string>(PALETTE[0].ink);
  const [current, setCurrent] = useState<Point[] | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [ids, setIds] = useState<string[]>([]);
  const [manual, setManual] = useState<string[] | null>(null);
  const [hoveredStroke, setHoveredStroke] = useState<number | null>(null);
  /**
   * Which note is being written in, if any.
   *
   * Writing is a mode and it has to be possible to leave it. While a note is
   * being written its shape carries handles and its field takes the pointer;
   * once it is committed the shape is just ink again, so the next line can be
   * drawn straight out of it.
   */
  const [editing, setEditing] = useState<string | null>(null);
  /**
   * The marks the reader has picked out, to move, resize or erase together.
   *
   * Shift-drag draws a rubber band over the mark-up layer; a plain click picks
   * out one. Nothing here selects the canvas's own elements -- those are
   * chosen by what the ink crosses, which is a different question.
   */
  const [selected, setSelected] = useState<Selection>(NOTHING_SELECTED);
  /** The rubber band, while it is being dragged. */
  const [marquee, setMarquee] = useState<{ a: Point; b: Point } | null>(null);
  /**
   * The element a line in progress would join, if it were let go now.
   *
   * Shown while drawing, so the reader knows before they commit whether this
   * is going to be a connection or a remark -- the difference matters and is
   * otherwise invisible until it is too late.
   */
  const [dropOn, setDropOn] = useState<string | null>(null);
  /**
   * The label in hand: clicked or dragged, so its cross is showing.
   *
   * A label and the line it sits on the end of are one object -- the line
   * exists to reach the words. So picking up either picks up both, and
   * deleting the label takes the line with it.
   */
  const [activeLabel, setActiveLabel] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  /** Remarks already sent, kept on the board as ghosts with their threads. */
  const [filed, setFiled] = useState<Filed[]>([]);
  /** The filed remark whose thread is open in the panel, if any. */
  const [openFiled, setOpenFiled] = useState<string | null>(null);
  /**
   * Applied changes the reader has said to keep. Local only: keeping a change
   * that is already on the canvas records nothing, it just lets the ghost go.
   * Putting one back is the real verb, and goes to the server.
   */
  const [kept, setKept] = useState<Set<string>>(() => new Set());
  /**
   * The pen held up off the page, while Space is down: the surface lets
   * everything through, so what the agent put on the board can be hovered
   * and opened -- an anchor, a card -- without leaving the mode. Release
   * and the pen is back, ink and mode untouched.
   */
  const [lifted, setLifted] = useState(false);
  /** The set-aside remark under the pointer, so its ground can say it is there. */
  const [hoverShelf, setHoverShelf] = useState<string | null>(null);
  const liftedRef = useRef(lifted);
  liftedRef.current = lifted;
  // The hand shows while the pen is up, since a drag now moves the board.
  useEffect(() => {
    if (!lifted) return undefined;
    document.body.dataset.penLifted = "";
    return () => {
      delete document.body.dataset.penLifted;
    };
  }, [lifted]);
  /** Remarks set aside unsent, each on its own ground. */
  const [shelf, setShelf] = useState<Stack[]>([]);
  const shelfRef = useRef(shelf);
  shelfRef.current = shelf;
  /** Which ground the live remark rests on. */
  const groundSeq = useRef(0);
  const [ground, setGround] = useState<string>(GHOST_GROUNDS[0]);
  const nextGround = () => {
    groundSeq.current += 1;
    return GHOST_GROUNDS[groundSeq.current % GHOST_GROUNDS.length] ?? GHOST_GROUNDS[0];
  };
  /** A tap that drew nothing; checked against the shelved grounds. */
  const tapRef = useRef<Point | null>(null);
  /** Where the reader carried the panel to; null is its resting place. */
  const [panelAt, setPanelAt] = useState<{ x: number; y: number } | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const panelDrag = useRef<{ startX: number; startY: number; x: number; y: number } | null>(null);
  /**
   * The reader has judged the last thing there was to judge: resolve the
   * intent, so its ghost goes and the queue count drops. Keeping and
   * putting back are both verdicts; a remark whose every suggestion has one
   * is finished. Left unresolved, a kept remark came back on every reload
   * as if it were still waiting.
   */
  const settle = async (intentId: string, judged: Set<string>) => {
    try {
      const it = await intents.get(intentId);
      if (!it || it.status !== "pending") return;
      const open = (it.items ?? []).some(
        (x) =>
          x.type === "suggestion" &&
          (x.state === "pending" ||
            (x.state === "applied" && x.author.kind !== "human" && !judged.has(x.id))),
      );
      if (!open) await intents.resolve(intentId, { verdict: "judged on the board" });
    } catch {
      // The next poll shows whatever state the server is in.
    }
  };
  /** Which question is being answered, and with what. */
  const [answering, setAnswering] = useState<{ item: string; text: string } | null>(null);

  const drawing = useRef(false);
  /** A stroke just landed: the click that ends it is not a click on it. */
  const drewJustNow = useRef(false);
  const strokesRef = useRef<Point[][]>([]);
  const marksRef = useRef<Mark[]>([]);
  const applyMarksRef = useRef<(next: Mark[]) => void>(() => {});
  const inkRef = useRef(ink);
  const notesRef = useRef<Note[]>([]);
  const boxesRef = useRef(boxes);
  const viewportRef = useRef(viewport);
  const surfaceRef = useRef<HTMLDivElement | null>(null);
  const marqueeDrag = useRef(false);
  const labelDrag = useRef<{ id: string; start: Point; from: Point } | null>(null);
  const labelLinesRef = useRef<Set<number>>(new Set());
  /** Which way the last offered remark went: the margin this page is using. */
  const marginDeg = useRef<number | null>(null);
  const activeLabelRef = useRef<string | null>(null);
  const removeLabelRef = useRef<(id: string) => void>(() => {});
  const selectedRef = useRef<Selection>(NOTHING_SELECTED);
  const onExitRef = useRef(onExit);
  /** The notes with their on-screen position and leader baked in; see snapshot. */
  const settledNotesRef = useRef<Note[]>([]);
  onExitRef.current = onExit;
  const removeSelectedRef = useRef<() => void>(() => {});
  const recolourRef = useRef<(color: string) => void>(() => {});
  /** A stroke being pulled at one place (option-drag on its ink). */
  const pullDrag = useRef<{ index: number; grab: Point; start: Point; points: Point[]; reach: number } | null>(null);
  const groupDrag = useRef<{
    mode: "move" | "resize";
    from: Rect;
    start: Point;
    anchor: Point;
    strokes: (readonly [number, Point[]])[];
    notes: (readonly [string, Point])[];
  } | null>(null);
  // The overlay swallows every gesture, so the two that are not drawing have
  // to be handed back. Marking up a board you cannot move is useless: the
  // remark is usually about something off screen.
  const panning = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);
  boxesRef.current = boxes;
  viewportRef.current = viewport;
  // Geometry, derived. Everything that reads strokes keeps reading points, and
  // the colours ride alongside on the same indices -- so there is no second
  // array to keep in step, which is where colour would otherwise drift.
  const strokes = marks.map((m) => m.points);
  strokesRef.current = strokes;
  marksRef.current = marks;
  inkRef.current = ink;

  /** The one way strokes change: ref first, so the same handler can read back. */
  const applyMarks = (next: Mark[]) => {
    marksRef.current = next;
    strokesRef.current = next.map((m) => m.points);
    setMarks(next);
  };
  applyMarksRef.current = applyMarks;
  notesRef.current = notes;

  const reset = useCallback(() => {
    marginDeg.current = null;
    setDropOn(null);
    setActiveLabel(null);
    applyMarksRef.current([]);
    setCurrent(null);
    setNotes([]);
    setIds([]);
    setManual(null);
    setHoveredStroke(null);
    setSelected(NOTHING_SELECTED);
    setMarquee(null);
  }, []);

  useEffect(() => {
    if (!active) {
      // Putting the pen down keeps the ink. Only what was mid-gesture goes:
      // a half-drawn stroke, a selection, a label being carried. What was
      // drawn is still there when the pen comes back,
      // the same as the agent's work on what was already filed. Clearing it
      // on the way out made escape, and the button, a way to lose a remark.
      setCurrent(null);
      setDropOn(null);
      setActiveLabel(null);
      setEditing(null);
      setHoveredStroke(null);
      setSelected(NOTHING_SELECTED);
      setMarquee(null);
    }
  }, [active]);

  // What was filed before this page loaded, rebuilt from the sketches the
  // server kept. Freehand ink does not survive a reload; the boxes do.
  useEffect(() => {
    let cancelled = false;
    void intents
      .listPending()
      .then((pending) => {
        if (cancelled) return;
        const mine = pending
          .filter((i) => i.origin_canvas_id === workspaceSlug)
          .map(filedFromIntent)
          .filter((f): f is Filed => f !== null);
        setFiled((prev) => {
          const have = new Set(prev.map((f) => f.intentId));
          return [...prev, ...mine.filter((f) => !have.has(f.intentId))];
        });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [workspaceSlug]);

  // Asking after each filed remark: its thread is where the agent's
  // progress, questions and proposal arrive. A push signal exists for the
  // count of pending intents but not for a thread growing, so this polls,
  // and refetches at once when anything in this window changes an intent.
  useEffect(() => {
    if (filed.length === 0) return undefined;
    let cancelled = false;
    const refresh = async () => {
      const latest = await Promise.all(
        filed.map(async (f) => {
          try {
            return await intents.get(f.intentId);
          } catch {
            return null;
          }
        }),
      );
      if (cancelled) return;
      setFiled((prev) =>
        prev
          .map((f) => {
            const got = latest.find((i) => i?.id === f.intentId);
            return got ? { ...f, intent: got } : f;
          })
          // Resolved and nothing left to judge: the ghost has done its job.
          // Resolving IS the judgement on what was applied -- keep and put
          // it back both resolve -- so only a suggestion still pending keeps
          // a resolved remark on the board. Judging by a set held in memory
          // meant a reload brought every kept remark back as unjudged.
          .filter((f) => {
            const it = f.intent;
            if (!it || it.status !== "resolved") return true;
            return (it.items ?? []).some((x) => x.type === "suggestion" && x.state === "pending");
          }),
      );
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), THREAD_POLL_MS);
    const onChanged = () => void refresh();
    window.addEventListener(INTENTS_CHANGED_EVENT, onChanged);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener(INTENTS_CHANGED_EVENT, onChanged);
    };
    // Re-arm when the SET of filed remarks changes, not on every poll result.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filed.map((f) => f.intentId).join("|"), workspaceSlug]);

  const toFlow = useCallback(
    (e: { clientX: number; clientY: number }) =>
      screenToFlowPosition({ x: e.clientX, y: e.clientY }),
    [screenToFlowPosition],
  );

  /**
   * Everything outside the visible canvas, as four occupied bands.
   *
   * An offer that lands off screen is an offer nobody sees: the ring's left
   * side was clear in canvas terms and under the tool rail in real ones. The
   * inset keeps the words off the rails and panels that sit over the edges.
   */
  const offScreen = (): Rect[] => {
    const el = surfaceRef.current;
    if (!el) return [];
    const r = el.getBoundingClientRect();
    const inset = 64;
    const tl = toFlow({ clientX: r.left + inset, clientY: r.top + inset });
    const br = toFlow({ clientX: r.right - inset, clientY: r.bottom - inset });
    const big = 1e6;
    return [
      { x: tl.x - big, y: tl.y - big, width: big, height: big * 2 },
      { x: br.x, y: tl.y - big, width: big, height: big * 2 },
      { x: tl.x - big, y: tl.y - big, width: big * 2, height: big },
      { x: tl.x - big, y: br.y, width: big * 2, height: big },
    ];
  };

  const onPointerDown = (e: React.PointerEvent) => {
    if (!active) return;
    if (e.button === 1) {
      e.preventDefault();
      const vp = getViewport();
      panning.current = { x: e.clientX, y: e.clientY, vx: vp.x, vy: vp.y };
      (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
      return;
    }
    if (e.button !== 0) return;
    // Starting to draw is leaving the text. Reaching for the canvas is a
    // clear enough statement that the note is finished; asking for enter as
    // well would mean the first stroke of the next mark went into the
    // previous one's words.
    if (editing) {
      setEditing(null);
      (document.activeElement as HTMLElement | null)?.blur();
    }
    // Shift draws a rubber band over the mark-up instead of drawing on it,
    // for picking out several marks at once.
    if (e.shiftKey) {
      e.preventDefault();
      e.stopPropagation();
      (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
      marqueeDrag.current = true;
      const p = toFlow(e);
      setSelected(NOTHING_SELECTED);
      setMarquee({ a: p, b: p });
      return;
    }
    // Starting anything else withdraws an offer nobody took up.
    setNotes((prev) => prev.filter((n) => !n.offered || n.text.trim()));
    // cmd/ctrl-click corrects the proposal rather than starting over.
    if (e.metaKey || e.ctrlKey) {
      setSelected(NOTHING_SELECTED);
      setActiveLabel(null);
      return;
    }
    // Pressing on the ink of a drawn shape takes hold of it: drag and it
    // moves, let go without moving and it is picked out. There used to be a
    // tab to pull, and reaching for a tab is a detour when the line itself
    // is right under the hand. A shape that is already part of a selection
    // carries the whole selection with it.
    {
      const p = toFlow(e);
      const hit = strokeAt(p, strokesRef.current, 10 / Math.max(0.1, viewportRef.current.zoom));
      if (hit >= 0 && !labelLinesRef.current.has(hit)) {
        // Option held: pull the line here rather than move the shape. The
        // reach is a quarter of the line, so a ring drawn a row short is
        // pulled over the row without the rest of it going anywhere.
        if (e.altKey) {
          e.preventDefault();
          e.stopPropagation();
          (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
          const points = strokesRef.current[hit]!;
          let length = 0;
          for (let i = 1; i < points.length; i++) {
            length += Math.hypot(points[i]!.x - points[i - 1]!.x, points[i]!.y - points[i - 1]!.y);
          }
          pullDrag.current = { index: hit, grab: p, start: p, points, reach: length / 4 };
          setSelected(NOTHING_SELECTED);
          setActiveLabel(null);
          return;
        }
        const inSelection = selectedRef.current.strokes.includes(hit);
        if (!inSelection) {
          setSelected(NOTHING_SELECTED);
          setActiveLabel(null);
        }
        startGroupDrag("move", undefined, inSelection ? selectedRef.current : { strokes: [hit], notes: [] })(e);
        return;
      }
    }
    // ...and puts down whatever was picked out, since the next gesture is a
    // new mark rather than something to do with the old ones.
    setSelected(NOTHING_SELECTED);
    setActiveLabel(null);
    e.preventDefault();
    e.stopPropagation();
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    drawing.current = true;
    setHoveredStroke(null);
    setCurrent([toFlow(e)]);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (groupDrag.current) {
      onGroupDragMove(e);
      return;
    }
    const pull = pullDrag.current;
    if (pull) {
      const p = toFlow(e);
      const next = pullStroke(pull.points, pull.grab, { x: p.x - pull.start.x, y: p.y - pull.start.y }, pull.reach);
      const nextStrokes = strokesRef.current.map((st, i) => (i === pull.index ? next : st));
      applyMarks(marksRef.current.map((m, i) => ({ ...m, points: nextStrokes[i]! })));
      setIds(manual ?? markHits(nextStrokes, boxesRef.current));
      return;
    }
    const pan = panning.current;
    if (pan) {
      const vp = getViewport();
      setViewport({
        zoom: vp.zoom,
        x: pan.vx + (e.clientX - pan.x),
        y: pan.vy + (e.clientY - pan.y),
      });
      return;
    }
    const p = toFlow(e);
    if (marqueeDrag.current) {
      setMarquee((m) => (m ? { ...m, b: p } : m));
      return;
    }
    if (!drawing.current) {
      // Which drawn stroke is under the pointer, so its × can appear.
      const slack = 10 / Math.max(0.1, viewportRef.current.zoom);
      const hit = strokeAt(p, strokesRef.current, slack);
      const next = hit >= 0 && !labelLinesRef.current.has(hit) ? hit : null;
      setHoveredStroke((prev) => (prev === next ? prev : next));
      const over = next === null ? shelfAt(p) : null;
      setHoverShelf((prev) => (prev === over ? prev : over));
      return;
    }
    setCurrent((prev) => {
      const nextStroke = prev ? [...prev, p] : [p];
      // Live, so the reader watches a line become a ring.
      setIds(markHits([...strokesRef.current, nextStroke], boxesRef.current));
      setManual(null);
      const slack = SNAP_PX / Math.max(0.1, viewportRef.current.zoom);
      const onto = isLoop(nextStroke)
        ? null
        : dropTarget(nextStroke, boxesRef.current, slack);
      // A ring is never a connector: it encloses what it is about.
      setDropOn((cur) => (cur === (onto?.id ?? null) ? cur : (onto?.id ?? null)));
      return nextStroke;
    });
  };

  const onPointerUp = (e?: React.PointerEvent) => {
    if (groupDrag.current && e) {
      endGroupDrag(e);
      return;
    }
    if (pullDrag.current) {
      pullDrag.current = null;
      drewJustNow.current = true;
      return;
    }
    panning.current = null;
    if (marqueeDrag.current) {
      marqueeDrag.current = false;
      setMarquee((m) => {
        if (m) setSelected(withinBand(rectFrom(m.a, m.b), strokesRef.current, notesRef.current));
        return null;
      });
      return;
    }
    if (!drawing.current) return;
    drawing.current = false;
    // After the stroke has been judged: a tap that drew nothing, landing on
    // a set-aside remark's ground, switches to it.
    window.setTimeout(() => {
      const at = tapRef.current;
      tapRef.current = null;
      if (!at) return;
      const hit = shelfAt(at);
      if (hit) switchToRef.current(hit);
    }, 0);
    setCurrent((cur) => {
      // A click leaves a dot. It is a mis-aim or a moment's hesitation, never
      // a remark, and keeping it litters the layer with specks nobody meant.
      // On the ground of a remark set aside, though, it is a choice: that
      // one comes back to the pen.
      if (!cur || cur.length < 2 || strokeLength(cur) < MIN_STROKE_PX) {
        if (cur?.[0]) tapRef.current = cur[0];
        return null;
      }
      // Dropped on something: the line is a join. Its tail is trimmed to the
      // edge it met, so it reads as attached rather than drawn across, and
      // both ends are recorded -- that pair is the whole content of the
      // gesture, and it needs no words to be understood.
      const slack = SNAP_PX / Math.max(0.1, viewportRef.current.zoom);
      const onto = isLoop(cur) ? null : dropTarget(cur, boxesRef.current, slack);
      const start = cur[0]!;
      const leftFrom =
        boxesRef.current.find(
          (b) => b.id !== onto?.id && nearRect(start, b, slack),
        )?.id ?? null;
      const points = onto ? clipToBox(cur, onto) : cur;
      // Ring a thing, carry on out to where the words go: one movement of the
      // hand, but two marks. They are cut apart here, as they are drawn, so
      // afterwards they are simply independent -- the ring stays put while
      // the line swings, with no surgery at drag time and no stub of tail
      // left curling about inside the ring.
      const split = onto ? null : loopAndTail(cur);
      const line = split ? lineOutOfLoop(split.loop, split.tail) : [];
      // A line out of a drawn shape is part of that shape's remark, so it
      // takes the shape's pen rather than whichever is in hand.
      const shapeIndex =
        isLoop(cur) || split
          ? -1
          : marksRef.current.findIndex((m) => {
              if (!isLoop(m.points)) return false;
              const outline = ringOutline(m.points);
              return outline.length >= 3 && insidePolygon(cur[0]!, outline);
            });
      const pen = shapeIndex >= 0 ? marksRef.current[shapeIndex]!.color : inkRef.current;
      applyMarks([
        ...marksRef.current,
        ...(split && line.length > 1
          ? [
              { points: split.loop, color: inkRef.current },
              { points: line, color: inkRef.current },
            ]
          : [
              {
                points,
                color: pen,
                ...(onto ? { link: { from: leftFrom, to: onto.id } } : {}),
              },
            ]),
      ]);
      const next = strokesRef.current;
      drewJustNow.current = true;
      setDropOn(null);
      const hits = markHits(next, boxesRef.current);
      setIds(hits);
      // What THIS shape caught, which is a different question from what the
      // whole mark is about. Judging by the mark meant a fresh box drawn on
      // empty canvas inherited the hits of an earlier stroke, and was offered
      // a leader out to a card it had nothing to do with.
      const caught = lassoHits(cur, boxesRef.current);
      // Every ring that catches something gets its own offer. Gating on "no
      // notes at all" meant the first remark used up the offer for the whole
      // mark: ringing a second thing left the reader with nowhere to type and
      // no sign of why. Only an offer nobody has taken blocks another.
      const pendingOffer = notesRef.current.some((n) => n.offered && !n.text.trim());
      // A closed shape drawn on open canvas is not pointing at anything: it
      // IS the place for the words. Offering a leader out to a field beside it
      // would answer a question nobody asked, and leave the reader with a box
      // they drew to write in and a cursor somewhere else.
      if (caught.length === 0 && isLoop(cur) && !pendingOffer) {
        const id = `n${Date.now()}`;
        const bounds = strokeBounds(cur);
        setNotes((prev) => [
          ...prev,
          {
            id,
            x: bounds.x,
            y: bounds.y,
            text: "",
            inStroke: next.length - 1,
            offered: true,
            color: inkRef.current,
          },
        ]);
        setEditing(id);
        return null;
      }
      // A line that LEAVES something the reader drew is a leader, whether or
      // not it touched a card on the way: they drew a shape, then drew out of
      // it to say something about it. Offering nothing because the shape
      // held no card left the line ending in silence.
      const leftShape =
        isLoop(cur) || split
          ? -1
          : strokesRef.current.findIndex((st, i) => {
              if (i >= strokesRef.current.length - 1 || !isLoop(st)) return false;
              const outline = ringOutline(st);
              return outline.length >= 3 && insidePolygon(cur[0]!, outline);
            });
      const leavesAShape = leftShape >= 0;
      // A join says what it means with its two ends, so no words are offered.
      if ((caught.length > 0 || leavesAShape) && !pendingOffer && !onto) {
        const id = `n${Date.now()}`;
        if (isLoop(cur)) {
          // A ring is not going anywhere: it encloses. The words go out to
          // open canvas, and the line that reaches them comes from the middle
          // of the ring -- so wherever they are carried afterwards, the line
          // still reads as coming out of the thing that was ringed.
          // The same short line out as words called out down a card's side
          // get, measured from the rim of the ring rather than a multiple of
          // its size from the middle: a ring round two cards was sending its
          // words as far away as the ring was wide.
          const bounds = strokeBounds(cur);
          const zoom = Math.max(0.2, viewportRef.current.zoom);
          const gap = CALLOUT_GAP_PX / zoom;
          const outline = ringOutline(cur);
          const centre = loopCentre(outline);
          const reach =
            outline.length >= 3
              ? rimReach(outline, centre)
              : Math.max(bounds.width, bounds.height) / 2;
          const at = clearSpot(
            centre,
            reach,
            gap,
            { width: NOTE_W, height: NOTE_H },
            [
              ...boxesRef.current,
              // Not the ring itself: its bounding box is what the words are
              // being placed outside of, and counting it blocked every
              // direction but straight up and down for a ring of any size.
              ...strokesRef.current.filter((_, i) => i !== next.length - 1).map(strokeBounds),
              ...notesRef.current.filter((n) => n.inStroke === undefined).map(noteRect),
              ...offScreen(),
            ],
            gap / 2,
            marginDeg.current ?? undefined,
          );
          // Remember which way this one went, so the next lines up with it --
          // when it went sideways. A margin is a side of the page; an offer
          // that had to go up or down was making do, and remembering it sent
          // the next ring's words straight down past two clear sides.
          const went = (Math.atan2(at.y - centre.y, at.x - centre.x) * 180) / Math.PI;
          marginDeg.current =
            Math.abs(Math.cos((went * Math.PI) / 180)) >= Math.SQRT1_2 ? went : null;
          setNotes((prev) => [
            ...prev,
            {
              id,
              x: at.x,
              y: at.y,
              text: "",
              ringStroke: next.length - 1,
              offered: true,
              color: inkRef.current,
            },
          ]);
        } else {
          // A line already IS a leader: the reader drew it to point somewhere.
          // Inventing a second one sent the words off at an angle nobody drew
          // -- and put a second dashed line on the page to explain it.
          //
          // Where the gesture was cut in two, the words belong to the line,
          // not to the ring: dragging them swings the connector and leaves
          // the encirclement on what it was drawn around.
          const { end, from } = strokeHeading(split && line.length > 1 ? line : cur);
          setNotes((prev) => [
            ...prev,
            {
              id,
              x: end.x,
              y: end.y,
              text: "",
              from,
              continues: true,
              onStroke: next.length - 1,
              // Where the gesture was cut in two, the ring is the mark just
              // before the line. The words know about both, so removing them
              // takes the whole gesture rather than leaving a ring behind
              // highlighting something nobody is talking about any more.
              ...(split && line.length > 1 ? { ringStroke: next.length - 2 } : {}),
              offered: true,
              color: inkRef.current,
            },
          ]);
        }
        setEditing(id);
      }
      return null;
    });
  };

  // Double-click puts a comment where you double-clicked. Inside a shape that
  // was drawn, the box becomes the thing you wrote in.
  const onDoubleClick = (e: React.PointerEvent) => {
    if (!active) return;
    e.preventDefault();
    e.stopPropagation();
    const p = toFlow(e);
    const inside = strokesRef.current.findIndex((st) => insideStroke(p, st));
    // Writing in a shape that already holds words picks those words back up.
    // Adding a second note in the same box would stack two lots of text in
    // one place, and the reader meant to edit what is there.
    const existing = notesRef.current.find((n) =>
      inside >= 0 ? n.inStroke === inside : hitsNote(p, n),
    );
    if (existing) {
      setEditing(existing.id);
      return;
    }
    const id = `n${Date.now()}`;
    setNotes((prev) => [
      ...prev.filter((n) => !n.offered || n.text.trim()),
      {
        id,
        x: p.x,
        y: p.y,
        text: "",
        color: inkRef.current,
        ...(inside >= 0 ? { inStroke: inside } : {}),
      },
    ]);
    setEditing(id);
  };

  const onClick = (e: React.PointerEvent) => {
    if (!active) return;
    // A plain click on a mark picks it out, which is what puts handles on it.
    // Hover used to be enough, and that made every shape the pointer crossed
    // sprout eight targets to catch the next stroke.
    if (!e.metaKey && !e.ctrlKey) {
      if (drewJustNow.current) {
        drewJustNow.current = false;
        return;
      }
      const p = toFlow(e);
      // Strokes only. The words at the end of a leader are not a box to be
      // pulled and sized -- they are the remark itself, and wrapping them in
      // handles turned every comment into an object to be managed. A drawn
      // shape is the thing that has a size worth dragging.
      const hit = strokeAt(p, strokesRef.current, 10 / Math.max(0.1, viewportRef.current.zoom));
      const own = hit >= 0 && !labelLinesRef.current.has(hit);
      setSelected(own ? { strokes: [hit], notes: [] } : NOTHING_SELECTED);
      // Clicking a label's line is clicking the label: one object.
      const owner =
        hit >= 0 && !own
          ? (notesRef.current.find((n) => n.onStroke === hit)?.id ?? null)
          : null;
      setActiveLabel(owner);
      return;
    }
    const p = toFlow(e);
    const hit = [...boxesRef.current]
      .reverse()
      .find((b) => p.x >= b.x && p.x <= b.x + b.width && p.y >= b.y && p.y <= b.y + b.height);
    if (!hit) return;
    e.preventDefault();
    e.stopPropagation();
    setIds((prev) => {
      const next = toggleId(prev, hit.id);
      setManual(next);
      return next;
    });
  };

  /** Put a stroke back with new geometry, leaving everything else alone. */
  const replaceStroke = (index: number, points: Point[]) => {
    if (!marksRef.current[index]) return;
    applyMarks(
      marksRef.current.map((m, i) => (i === index ? { ...m, points } : m)),
    );
    setIds(manual ?? markHits(strokesRef.current, boxesRef.current));
  };

  /**
   * Make a drawn shape tall enough for what has been written in it.
   *
   * It grows downward, keeping the top edge where the reader put it, because
   * the words start at the top and growth should push the bottom away rather
   * than move the whole shape out from under the cursor.
   */
  const growHost = (index: number, neededHeight: number) => {
    const stroke = strokesRef.current[index];
    if (!stroke) return;
    const b = strokeBounds(stroke);
    if (b.height >= neededHeight - 0.5) return;
    replaceStroke(index, fitStroke(stroke, { ...b, height: neededHeight }));
  };

  /**
   * What the selection covers: every mark in it, as one box.
   *
   * Handles hang off this rather than off each mark, so a group scales by one
   * transform and a stroke in the corner of the selection stays in the corner
   * instead of being stretched to fill the whole box on its own.
   */
  const rectOf = (sel: Selection): Rect | null =>
    unionRect([
      ...sel.strokes
        .map((i) => strokesRef.current[i])
        .filter((st): st is Point[] => st !== undefined)
        .map(strokeBounds),
      ...sel.notes
        .map((id) => notesRef.current.find((n) => n.id === id))
        .filter((n): n is Note => n !== undefined)
        .map(noteRect),
    ]);

  const selectionRect = (): Rect | null => rectOf(selected);

  /**
   * Start dragging the selection, to move it or to resize it.
   *
   * The marks are captured as they were when the drag began and the transform
   * is applied to THOSE each time, rather than to the result of the last move.
   * Compounding the transform instead would let rounding accumulate, and a
   * shape dragged back and forth would slowly wander and distort.
   *
   * The pointer is captured on the handle: without it, the first move outside
   * the little square lands on the drawing surface and starts a new stroke
   * across the very thing being dragged.
   */
  const startGroupDrag =
    (mode: "move" | "resize", corner?: { x: 0 | 1; y: 0 | 1 }, over?: Selection) =>
    (e: React.PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      // A tab on one stroke drags that stroke. The handles on the selection
      // drag the selection. Same machinery, different set of marks.
      const sel = over ?? selected;
      const from = rectOf(sel);
      if (!from) return;
      groupDrag.current = {
        mode,
        from,
        start: toFlow(e),
        anchor: corner
          ? {
              x: corner.x === 0 ? from.x + from.width : from.x,
              y: corner.y === 0 ? from.y + from.height : from.y,
            }
          : { x: from.x, y: from.y },
        strokes: sel.strokes
          .map((i) => [i, strokesRef.current[i]] as const)
          .filter((pair): pair is readonly [number, Point[]] => pair[1] !== undefined),
        notes: sel.notes
          .map((id) => notesRef.current.find((n) => n.id === id))
          .filter((n): n is Note => n !== undefined)
          .map((n) => [n.id, { x: n.x, y: n.y }] as const),
      };
      e.currentTarget.setPointerCapture(e.pointerId);
    };

  const onGroupDragMove = (e: React.PointerEvent) => {
    const g = groupDrag.current;
    if (!g) return;
    e.stopPropagation();
    const p = toFlow(e);
    const to: Rect =
      g.mode === "move"
        ? { ...g.from, x: g.from.x + (p.x - g.start.x), y: g.from.y + (p.y - g.start.y) }
        : (() => {
            const width = Math.max(MIN_BOX_PX, Math.abs(p.x - g.anchor.x));
            const height = Math.max(MIN_BOX_PX, Math.abs(p.y - g.anchor.y));
            return {
              x: p.x < g.anchor.x ? g.anchor.x - width : g.anchor.x,
              y: p.y < g.anchor.y ? g.anchor.y - height : g.anchor.y,
              width,
              height,
            };
          })();

    const nextStrokes = [...strokesRef.current];
    for (const [index, points] of g.strokes) {
      nextStrokes[index] =
        g.mode === "move"
          ? translateStroke(points, to.x - g.from.x, to.y - g.from.y)
          : remapStroke(points, g.from, to);
    }
    applyMarks(marksRef.current.map((m, i) => ({ ...m, points: nextStrokes[i]! })));
    setIds(manual ?? markHits(nextStrokes, boxesRef.current));
    if (g.notes.length > 0) {
      setNotes((prev) =>
        prev.map((n) => {
          const orig = g.notes.find(([id]) => id === n.id)?.[1];
          if (!orig) return n;
          const at = remapPoint(orig, g.from, to);
          return { ...n, x: at.x, y: at.y };
        }),
      );
    }
  };

  const endGroupDrag = (e: React.PointerEvent) => {
    const g = groupDrag.current;
    if (!g) return;
    groupDrag.current = null;
    e.stopPropagation();
    // Let go where it was pressed: a click, and the click that follows picks
    // the mark out. Let go somewhere else: a move, and the click that
    // follows is not a click.
    const p = toFlow(e);
    if (Math.hypot(p.x - g.start.x, p.y - g.start.y) * viewportRef.current.zoom > 3) {
      drewJustNow.current = true;
    }
  };

  /**
   * Give everything picked out a new pen.
   *
   * Nothing picked out means nothing to recolour -- the key has already set
   * the pen in hand, which is what it does the rest of the time.
   */
  const recolourSelected = (color: string) => {
    if (selected.strokes.length === 0 && selected.notes.length === 0) return;
    const inSelection = new Set(selected.strokes);
    applyMarks(
      marksRef.current.map((m, i) => (inSelection.has(i) ? { ...m, color } : m)),
    );
    const notesToo = new Set(selected.notes);
    setNotes((prev) =>
      prev.map((n) =>
        notesToo.has(n.id) || (n.inStroke !== undefined && inSelection.has(n.inStroke))
          ? { ...n, color }
          : n,
      ),
    );
  };

  /**
   * Carry a label somewhere else, and let its leader follow.
   *
   * Only the far end moves. The line keeps the end it started from, so it
   * pivots and stretches about that point, and the words re-lean to carry on
   * the new angle -- which is what a leader is for. Dragging a label that was
   * simply sitting at the end of a drawn line pulls it off that end, so the
   * connector appears: the reader has separated the two, and a line is what
   * says they still belong together.
   */
  const moveLabel = (id: string, to: Point) => {
    const note = notesRef.current.find((n) => n.id === id);
    if (!note) return;
    // Words at the end of a line the reader drew: the LINE follows them. It
    // swings and stretches about the point it started from, so one gesture
    // stays one line. Leaving the stroke where it was and running a connector
    // out to the words put an elbow in the middle of it.
    const i = note.onStroke;
    if (i !== undefined && marksRef.current[i]) {
      // The line is a mark of its own, and its first point sits on the edge
      // of whatever it left. Swinging it about that point keeps it attached
      // there, and touches nothing else.
      const swung = pivotStroke(marksRef.current[i]!.points, to);
      applyMarks(marksRef.current.map((m, k) => (k === i ? { ...m, points: swung } : m)));
      setIds(manual ?? markHits(strokesRef.current, boxesRef.current));
      const { end, from } = strokeHeading(swung);
      setNotes((prev) =>
        prev.map((n) => (n.id === id ? { ...n, x: end.x, y: end.y, from } : n)),
      );
      return;
    }
    // Words at the end of a leader the app offered: only the far end moves,
    // so the leader pivots about where it met the ink. Carrying them by hand
    // pins them, so the callout layout stops moving them about.
    setNotes((prev) =>
      prev.map((n) => (n.id === id ? { ...n, x: to.x, y: to.y, pinned: true } : n)),
    );
  };

  /**
   * Take a label and the line it belongs to.
   *
   * The line was drawn to reach the words; without them it is a stroke
   * pointing at nothing, left behind to be tidied up by hand. A label at the
   * end of an offered leader needs no such care -- that leader is drawn from
   * the note itself, so it goes when the note does.
   */
  /**
   * Take strokes off the board, and everything hanging off them.
   *
   * A highlight is one gesture drawn as three marks: the ring, the line
   * out of it, and the words at the end. Deleting any one of them deletes
   * the gesture; leaving a ring with no words is a circle round something
   * for no stated reason, and leaving words with no ring is a remark about
   * nothing. So the set to remove is closed over those links first. Notes
   * point at strokes by index, and dropping some shifts the rest, which
   * every path here used to get subtly wrong for one of the three kinds.
   */
  const dropMarks = (strokes: Iterable<number>, noteIds: Iterable<string> = []) => {
    const gone = new Set(strokes);
    const goneNotes = new Set(noteIds);
    // Close over the gesture: a note whose ring or line is going takes its
    // other marks with it; a note going takes its ring and line.
    let grew = true;
    while (grew) {
      grew = false;
      for (const n of notesRef.current) {
        const linked = [n.onStroke, n.ringStroke].filter((i): i is number => i !== undefined);
        const hit = goneNotes.has(n.id) || linked.some((i) => gone.has(i));
        if (!hit) continue;
        if (!goneNotes.has(n.id)) {
          goneNotes.add(n.id);
          grew = true;
        }
        for (const i of linked) {
          if (!gone.has(i)) {
            gone.add(i);
            grew = true;
          }
        }
      }
    }
    const kept = strokesRef.current.filter((_, i) => !gone.has(i));
    const shift = (i: number) => i - [...gone].filter((g) => g < i).length;
    const re = (i: number | undefined) => (i === undefined || gone.has(i) ? undefined : shift(i));
    applyMarks(marksRef.current.filter((_, i) => !gone.has(i)));
    setNotes((prev) =>
      prev
        .filter((n) => !goneNotes.has(n.id))
        .filter((n) => n.inStroke === undefined || !gone.has(n.inStroke))
        .map((n) => ({
          ...n,
          inStroke: re(n.inStroke),
          onStroke: re(n.onStroke),
          ringStroke: re(n.ringStroke),
        })),
    );
    setIds(manual ?? markHits(kept, boxesRef.current));
    setSelected(NOTHING_SELECTED);
    setActiveLabel(null);
    setHoveredStroke(null);
  };

  const removeLabel = (id: string) => dropMarks([], [id]);

  /** Erase everything in the selection at once. */
  const removeSelected = () => dropMarks(selected.strokes, selected.notes);

  /** Remove one stroke, and the gesture it was part of. */
  const removeStroke = (index: number) => dropMarks([index]);

  /**
   * Put the remark in hand on the pile and start a clean one.
   *
   * The strokes are captured BEFORE the ref is reset: a state updater runs
   * when React gets round to it, by which point the ref is already the empty
   * array for the next remark, and the queued ink vanished.
   */
  /** The live remark as it would be queued, without queueing it. */
  const snapshot = (text: string, id = `q${Date.now()}`): Queued => {
    // The notes are taken as they stand on screen -- called out beside a
    // card, with the leader that reaches them -- since after queueing
    // nothing recomputes either, and the words used to jump to where they
    // were first offered and lose their line.
    const drawn = marksRef.current;
    const written = settledNotesRef.current.filter((n) => n.text.trim());
    const sketch = resolveSketch(
      drawn.map((m) => m.points),
      written,
      boxesRef.current,
    );
    const cuts = resolveCuts(drawn.map((m) => m.points), boxesRef.current, rowsOf);
    const strikes = resolveStrikes(drawn.map((m) => m.points), edgesOf());
    return { id, text, ids, sketch, cuts, strikes, marks: drawn, notes: written };
  };

  /** Where a set-aside remark's ground lies, in canvas coordinates. */
  const blobOf = (st: Pick<Stack, "marks" | "notes" | "ids">): Point[] | null => {
    const corners: Point[] = [
      ...st.marks.flatMap((m) => m.points),
      ...st.notes.filter((n) => n.inStroke === undefined).flatMap((n) => rectCorners(noteRect(n))),
      ...boxesRef.current.filter((b) => st.ids.includes(b.id)).flatMap(rectCorners),
    ];
    if (corners.length < 3) return null;
    const shape = blobAround(corners, BLOB_PAD_PX / Math.max(0.2, viewportRef.current.zoom));
    return shape.length >= 3 ? shape : null;
  };

  /** The set-aside remark whose ground is under a canvas point, if any. */
  const shelfAt = (at: Point): string | null => {
    const hit = shelfRef.current.find((st) => {
      const b = blobOf(st);
      return b ? insidePolygon(at, b) : false;
    });
    return hit?.id ?? null;
  };

  /** Bring a remark's ground into view when it is off the screen. */
  const reveal = (st: Pick<Stack, "marks" | "notes" | "ids">) => {
    const b = blobOf(st);
    const el = surfaceRef.current;
    if (!b || !el) return;
    const vp = getViewport();
    const xs = b.map((pt) => pt.x * vp.zoom + vp.x);
    const ys = b.map((pt) => pt.y * vp.zoom + vp.y);
    const r = el.getBoundingClientRect();
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    if (x0 >= 0 && y0 >= 0 && x1 <= r.width && y1 <= r.height) return;
    const cx = (x0 + x1) / 2;
    const cy = (y0 + y1) / 2;
    setViewport({ zoom: vp.zoom, x: vp.x + r.width / 2 - cx, y: vp.y + r.height / 2 - cy }, { duration: 300 });
  };

  /** Set the live remark aside on its ground, unsent, and clear the pen. */
  const shelveLive = () => {
    if (marksRef.current.length === 0 && !notesRef.current.some((n) => n.text.trim())) return;
    const text = notesRef.current.map((n) => n.text.trim()).filter(Boolean).join("\n\n");
    const entry: Stack = { ...snapshot(text), ground };
    setShelf((prev) => [...prev, entry]);
    reset();
  };

  /**
   * A fresh remark, with the current one set aside rather than sent.
   *
   * The next stroke after sending is already a new remark; this is for the
   * ask that comes to mind before the last one is finished.
   */
  const newStack = () => {
    if (marksRef.current.length === 0 && !notesRef.current.some((n) => n.text.trim())) return;
    shelveLive();
    setGround(nextGround());
    // A fresh remark starts in a fresh pen: the first one no remark on the
    // board is using, so the new ink is never the ink of the one just set
    // aside. When every pen is in use, the next one along.
    const used = new Set([
      ...marksRef.current.map((m) => m.color),
      ...shelfRef.current.flatMap((st) => st.marks.map((m) => m.color)),
      ...filed.flatMap((f) => f.marks.map((m) => m.color)),
      ink,
    ]);
    const at = PALETTE.findIndex((pen) => pen.ink === ink);
    const order = [...PALETTE.slice(at + 1), ...PALETTE.slice(0, at + 1)];
    const fresh = order.find((pen) => !used.has(pen.ink)) ?? order[0];
    if (fresh) setInk(fresh.ink);
  };

  /** Bring a set-aside remark back to the pen, setting the live one aside. */
  const switchTo = (id: string) => {
    const target = shelfRef.current.find((st) => st.id === id);
    if (!target) return;
    shelveLive();
    setShelf((prev) => prev.filter((st) => st.id !== id));
    applyMarks(target.marks);
    setNotes(target.notes.map((n) => ({ ...n, offered: false })));
    setIds(target.ids);
    setManual(target.ids);
    setGround(target.ground);
    // Its own pen back in hand, so the next stroke is the same ink as the
    // rest of the remark rather than the one just set aside.
    const pen = target.marks[target.marks.length - 1]?.color;
    if (pen) setInk(pen);
    setSelected(NOTHING_SELECTED);
    setActiveLabel(null);
  };
  const switchToRef = useRef(switchTo);
  switchToRef.current = switchTo;
  const newStackRef = useRef(newStack);
  newStackRef.current = newStack;

  /**
   * The remark goes to the agent as it stands, and its ink fades to a
   * ghost that stays until the intent is resolved.
   *
   * There used to be a queue between drawing and sending, so that sending
   * each thought would not wake the agent once per thought. The agent
   * listens now, and a remark is the unit of work: one remark can hold as
   * many rings, lines and words as the reader likes before they press send,
   * so batching happens on the board, not in a list. The next stroke after
   * sending is the next remark.
   */
  const sendRemark = async () => {
    if (sending) return;
    const q = snapshot(notesRef.current.map((n) => n.text.trim()).filter(Boolean).join("\n\n"));
    setSending(true);
    try {
      // The words, then the shape of the drawing under them. Both, because
      // not every reader will parse a structure and the two must never
      // disagree about what was drawn.
      const pointers = resolvePointers(q.notes, q.marks.map((m) => m.points), boxesRef.current, rowsOf);
      const drawn = [describeSketch(q.sketch), describeCuts(q.cuts), describeStrikes(q.strikes), describePointers(pointers)]
        .filter(Boolean)
        .join("\n");
      // A struck edge's two ends are what the ask is about, so they are
      // targets too: the cross itself caught no card.
      const ends = q.strikes.flatMap((k) => [k.source, k.target]);
      const created = await intents.create({
        text: !drawn ? q.text : q.text ? `${q.text}\n\n--- drawn ---\n${drawn}` : drawn,
        workspaceSlug,
        targets: Array.from(new Set([...q.ids, ...ends, ...pointers.map((pt) => pt.node)])),
        ...(q.sketch.nodes.length > 0 ? { sketch: q.sketch } : {}),
        ...(q.cuts.length > 0 ? { cuts: q.cuts } : {}),
        ...(q.strikes.length > 0 ? { strikes: q.strikes } : {}),
        ...(pointers.length > 0 ? { pointers } : {}),
      });
      // Sent, not gone: the remark stays on the board as the place its own
      // outcome will appear.
      setFiled((prev) => [
        ...prev,
        {
          intentId: created.id,
          text: q.text,
          ids: q.ids,
          sketch: q.sketch,
          marks: q.marks,
          notes: q.notes,
          color: q.marks[0]?.color ?? INK,
          ground,
          intent: created,
        },
      ]);
      reset();
      // The ghost keeps this ground; the next remark takes a fresh one.
      setGround(nextGround());
      onFiled?.();
    } catch (err) {
      // The remark is still on the board, untouched, so nothing is lost.
      window.alert(`Not sent: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSending(false);
    }
  };

  // A native non-passive listener: React's onWheel is passive and cannot stop
  // the page scrolling instead.
  useEffect(() => {
    if (!active) return undefined;
    const el = surfaceRef.current;
    if (!el) return undefined;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const vp = getViewport();
      const r = el.getBoundingClientRect();
      const px = e.clientX - r.left;
      const py = e.clientY - r.top;
      const next = Math.min(4, Math.max(0.1, vp.zoom * Math.exp(-e.deltaY * 0.0015)));
      // Keep whatever is under the pointer under the pointer.
      const fx = (px - vp.x) / vp.zoom;
      const fy = (py - vp.y) / vp.zoom;
      setViewport({ zoom: next, x: px - fx * next, y: py - fy * next });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [active, getViewport, setViewport]);

  useEffect(() => {
    if (!active) {
      setLifted(false);
      return undefined;
    }
    const typing = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      return t?.tagName === "INPUT" || t?.tagName === "TEXTAREA" || Boolean(t?.isContentEditable);
    };
    // With the pen up, a drag moves the board under it: the hand tool of
    // every drawing program, held on the same key. A trackpad has no middle
    // button, and leaving the mode just to look elsewhere lost the pen.
    let pan: { x: number; y: number; vx: number; vy: number } | null = null;
    const endPan = () => {
      pan = null;
      delete document.body.dataset.penPanning;
    };
    const onPanMove = (e: PointerEvent) => {
      if (!pan) return;
      setViewport({ zoom: getViewport().zoom, x: pan.vx + (e.clientX - pan.x), y: pan.vy + (e.clientY - pan.y) });
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.key === " " || e.code === "Space") setLifted(false);
    };
    // The pen is up to look, not to select. A press on a card would pick it
    // out and raise its toolbar, which is the canvas's business and not the
    // reason the pen went up. Anchors keep working: hovering one opens the
    // source and pressing one opens it for good. Anywhere else on the board
    // a press starts a pan. Caught in the capture phase, before the canvas's
    // own listeners hear of it.
    const onPress = (e: Event) => {
      if (!liftedRef.current) return;
      const t = e.target as HTMLElement | null;
      if (!t?.closest?.(".react-flow")) return;
      if (t.closest('[data-testid="ref-review-chip"], [data-source-anchor]')) return;
      e.stopPropagation();
      e.preventDefault();
      if (e.type === "pointerdown" && (e as PointerEvent).button === 0) {
        const pe = e as PointerEvent;
        const vp = getViewport();
        pan = { x: pe.clientX, y: pe.clientY, vx: vp.x, vy: vp.y };
        document.body.dataset.penPanning = "";
      }
    };
    // The pen goes down again if the window loses focus mid-hold, so a
    // cmd-tab away never leaves the surface transparent.
    const onBlur = () => {
      endPan();
      setLifted(false);
    };
    const onKey = (e: KeyboardEvent) => {
      // Keys typed into a field belong to the field. Escape there leaves the
      // words; here it would clear every mark on the board, and backspace
      // there deletes a letter, not the label being written in.
      if (typing(e)) return;
      if (e.key === " " || e.code === "Space") {
        e.preventDefault();
        if (!e.repeat) setLifted(true);
        return;
      }
      // 1-9 reach for a pen. A mark already picked out is recoloured instead,
      // so the same key means "this colour" whether the reader is about to
      // draw or has just pointed at something drawn.
      const pen = PALETTE.find((c) => c.key === e.key);
      if (pen && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        setInk(pen.ink);
        recolourRef.current(pen.ink);
        return;
      }
      // n: a new remark, the current one set aside unsent.
      if (e.key === "n" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        newStackRef.current();
        return;
      }
      // Delete takes what has been picked out. Nothing picked out means
      // nothing to delete -- it never falls through to clearing the mark.
      if (e.key === "Delete" || e.key === "Backspace") {
        if (activeLabelRef.current) {
          e.preventDefault();
          removeLabelRef.current(activeLabelRef.current);
          return;
        }
        if (selectedRef.current.strokes.length + selectedRef.current.notes.length === 0) return;
        e.preventDefault();
        removeSelectedRef.current();
        return;
      }
      if (e.key !== "Escape") return;
      // Escape puts the selection down first. Starting the whole mark over is
      // a bigger thing than letting go of what is picked out, and pressing
      // escape to get out of a selection should not cost the reader the lot.
      if (selectedRef.current.strokes.length + selectedRef.current.notes.length > 0) {
        setSelected(NOTHING_SELECTED);
        return;
      }
      // Nothing picked out: the only thing left to back out of is the mode.
      // Escape never clears the ink. It used to, when there was ink and no
      // selection, and one press too many after leaving a field wiped a
      // whole remark with no way back. The ink is kept and waits for the pen
      // to come back down; deleting is a selection and a delete key.
      onExitRef.current?.();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", onBlur);
    const presses = ["pointerdown", "mousedown", "click", "dblclick", "contextmenu"] as const;
    for (const type of presses) window.addEventListener(type, onPress, true);
    window.addEventListener("pointermove", onPanMove);
    window.addEventListener("pointerup", endPan);
    window.addEventListener("pointercancel", endPan);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onBlur);
      for (const type of presses) window.removeEventListener(type, onPress, true);
      window.removeEventListener("pointermove", onPanMove);
      window.removeEventListener("pointerup", endPan);
      window.removeEventListener("pointercancel", endPan);
      endPan();
    };
  }, [active, getViewport, setViewport]);

  if (!active) return null;

  const looping = current ? isLoop(current) : false;
  const all = current ? [...strokes, current] : strokes;
  // Flow coordinates to this overlay's own pixels. The overlay and the canvas
  // fill the same box, so the transform maps straight across.
  const screen = (p: Point) => ({
    x: p.x * viewport.zoom + viewport.x,
    y: p.y * viewport.zoom + viewport.y,
  });
  const paths = all.map((st) => st.map(screen));
  /**
   * Each filed remark's ghost: ink, shape, and everything the thread has put
   * on the board -- placed messages as ghost nodes, questions, the pending
   * suggestion. Worked out per render so it follows the poll.
   */
  const ghosts = filed.map((f) => {
    const items = f.intent?.items ?? [];
    const corners: Point[] = [
      ...f.marks.flatMap((m) => m.points),
      // The cards the remark caught. Without them the shape shrank to the
      // stroke the moment it was sent, and the status line landed on the
      // table it was about instead of beneath the whole of it.
      ...boxes.filter((b) => f.ids.includes(b.id)).flatMap(rectCorners),
      ...f.notes.filter((n) => n.inStroke === undefined).flatMap((n) => rectCorners(noteRect(n))),
      ...items.flatMap((it) =>
        it.place && it.type === "message" && it.state !== "done"
          ? [
              { x: it.place.x, y: it.place.y },
              {
                x: it.place.x + (it.place.width ?? GHOST_W),
                y: it.place.y + (it.place.height ?? GHOST_H),
              },
            ]
          : [],
      ),
    ];
    const pad = BLOB_PAD_PX / Math.max(0.2, viewport.zoom);
    const blob = corners.length >= 3 ? blobAround(corners, pad) : null;
    const status = [...items]
      .reverse()
      .find((it) => it.type === "message" && !it.place && it.author.kind !== "human");
    const questions = items.filter((it) => it.type === "question" && it.state === "open");
    const suggestion = [...items].reverse().find(
      (it) => it.type === "suggestion" && it.state === "pending",
    );
    // Act, then ask: a change the agent applied itself, which the reader has
    // not yet kept or put back. The result is on the canvas; the question is
    // only whether it stays.
    const applied =
      f.intent?.status === "resolved"
        ? undefined
        : [...items].reverse().find(
            (it) =>
              it.type === "suggestion" &&
              it.state === "applied" &&
              it.author.kind !== "human" &&
              !kept.has(it.id),
          );
    // Once there is a proposal, the plan has become the result: the agent's
    // ghost boxes stand down and the ops are drawn where they will land.
    const preview: Preview | null = suggestion?.ops
      ? previewOps(suggestion.ops, storeNodes, Object.values(storeEdges))
      : null;
    const placed = preview
      ? []
      : items.filter((it) => it.place && it.type === "message" && it.state !== "done");
    return { f, blob, status, questions, suggestion, applied, placed, items, preview };
  });

  // A mark with no words points at something without saying what about it.
  const written = notes.map((n) => n.text.trim()).filter(Boolean).join("\n\n");
  const cutsReading = resolveCuts(marks.map((m) => m.points), boxes, rowsOf);
  const strikesReading = resolveStrikes(marks.map((m) => m.points), edgesOf());
  // Some marks say it all by themselves. A cross over an edge or a line
  // through a table is the whole ask; demanding words as well made the
  // clearest gesture on the board the one that could not be sent.
  const sayable = Boolean(written) || cutsReading.length > 0 || strikesReading.length > 0;
  // Which shapes offer handles: the one under the pointer, and any that is
  // holding words. Closed shapes only -- a line has no box to pull on.
  // Strokes that belong to a label. They are not marks in their own right:
  // the label owns them, carries them when it moves and takes them when it is
  // deleted. Offering them their own cross put two of them on one gesture,
  // one at the end of the line and one on the words.
  const labelLines = new Set(
    notes.map((n) => n.onStroke).filter((i): i is number => i !== undefined),
  );
  /**
   * Words for highlights on a card, called out down its sides.
   *
   * Worked out on every render rather than stored, so they re-flow when one
   * is added or removed: the remaining remarks spread back out over the card
   * instead of leaving a gap where a deleted one used to be.
   */
  const calledOut = (() => {
    const byNode = new Map<string, { id: string; centre: Point }[]>();
    for (const n of notes) {
      if (n.pinned || n.ringStroke === undefined) continue;
      const ring = strokes[n.ringStroke];
      if (!ring) continue;
      // Called out only when the ring is about ONE card. A ring round two
      // put its words "beside the first card" -- which was the gap between
      // them, inside the ring, looking for all the world like a text box.
      // Several cards keep the clear-space placement outside the ring.
      const hits = lassoHits(ring, boxes);
      if (hits.length !== 1) continue;
      const on = hits[0]!;
      const list = byNode.get(on) ?? [];
      list.push({ id: n.id, centre: loopCentre(ringOutline(ring)) });
      byNode.set(on, list);
    }
    const out = new Map<string, CalloutPlace>();
    const gap = CALLOUT_GAP_PX / Math.max(0.2, viewport.zoom);
    for (const [nodeId, items] of byNode) {
      const node = boxes.find((b) => b.id === nodeId);
      if (!node) continue;
      for (const [id, place] of calloutPlaces(items, node, gap)) out.set(id, place);
    }
    return out;
  })();

  /** Where a note actually sits: called out by rule, or where it was carried. */
  const notePos = (n: Note): Point => {
    const place = calledOut.get(n.id);
    return place ? { x: place.x, y: place.y } : { x: n.x, y: n.y };
  };

  /**
   * Where a note's line begins.
   *
   * For a note that belongs to a ring this is recomputed rather than stored:
   * from the ring's centre, out through wherever the words are now, cut at
   * the outline. Storing the edge point would fix the line to one spot on the
   * rim, and carrying the words round to the far side would leave it hooking
   * back on itself.
   */
  const lineFrom = (n: Note): Point | undefined => {
    if (n.ringStroke === undefined) return n.from;
    const ring = strokes[n.ringStroke];
    if (!ring) return n.from;
    const outline = ringOutline(ring);
    if (outline.length < 3) return n.from;
    return exitLoop(outline, loopCentre(outline), notePos(n));
  };

  settledNotesRef.current = notes.map((n) => ({
    ...n,
    ...notePos(n),
    from: lineFrom(n) ?? n.from,
  }));

  /**
   * Everything this remark covers: the ink, the words, and the cards caught.
   *
   * Drawn as one quiet shape behind the lot, so the marks read as one remark
   * and the button that files them has something to belong to.
   */
  const remarkBlob = (() => {
    if (!sayable) return null;
    const corners: Point[] = [
      ...strokes.flat(),
      ...notes
        .filter((n) => n.inStroke === undefined)
        .flatMap((n) => rectCorners(noteRect({ ...n, ...notePos(n) }))),
      ...boxes.filter((b) => ids.includes(b.id)).flatMap(rectCorners),
    ];
    if (corners.length < 3) return null;
    const pad = BLOB_PAD_PX / Math.max(0.2, viewport.zoom);
    const shape = blobAround(corners, pad);
    return shape.length >= 3 ? shape : null;
  })();

  /**
   * The drawing as it currently reads, shown before it is filed.
   *
   * The reader is standing right here: if the shape of what they drew has
   * come out wrong, one line of readback lets them fix it in the second
   * before they send, which is worth more than any amount of interpretation
   * at the other end. It also makes "the structure was lost" and "the
   * structure was never read" tell each other apart, which from the filed
   * intent alone they do not.
   */
  const reading = resolveSketch(
    marks.map((m) => m.points),
    notes.filter((n) => n.text.trim()),
    boxes,
  );

  const picked = selectionRect();
  // Exactly one stroke and nothing else: it wears its controls on its own ink
  // rather than inside a box drawn round it.
  const lone =
    selected.strokes.length === 1 && selected.notes.length === 0
      ? selected.strokes[0]!
      : null;
  selectedRef.current = selected;
  removeSelectedRef.current = removeSelected;
  recolourRef.current = recolourSelected;
  activeLabelRef.current = activeLabel;
  labelLinesRef.current = labelLines;
  removeLabelRef.current = removeLabel;

  return (
    // One wrapper for every layer the pen lays over the canvas. It has no
    // box of its own; it carries the "pen up" mark that a stylesheet rule
    // turns into pointer-events none for everything inside, so what the
    // agent put on the board can be hovered through labels, handles and
    // verdict cards alike, not only through the drawing surface.
    <div className="contents" data-pen-up={lifted ? "" : undefined}>
      <svg
        data-testid="comment-lasso-ink"
        className="pointer-events-none absolute inset-0 z-30 h-full w-full"
      >
        {/* One shape around the whole remark. No border and barely a tint:
            it should say "these belong together" and nothing louder, since
            the marks themselves are what the reader is looking at. Neutral,
            not the pen's colour: a region is a grouping cue and the pens
            are the ink. Tinted with the current pen it changed colour the
            moment a second pen was picked up, and a blend of two pens would
            read as a third. */}
        {remarkBlob ? (
          <path
            data-testid="comment-lasso-blob"
            d={smoothClosedPath(remarkBlob.map(screen))}
            fill={ground}
            fillOpacity={0.14}
            stroke="none"
          />
        ) : null}

        {/* The march of an active ghost's border. One rule, defined once. */}
        <style>{`@keyframes anchor-ghost-march { to { stroke-dashoffset: -28; } }`}</style>

        {/* Filed remarks. Fainter than the pile: they are no longer the
            reader's to change, they are the agent's to answer. Each keeps
            its shape so the answer has somewhere to land. */}
        {ghosts.map(({ f, blob, suggestion }, i) => (
          <g key={`ghost-${f.intentId}`} data-testid="comment-lasso-ghost">
            {/* Each remark in flight on its own ground. Two remarks in the
                same pen were the same tint, and where their shapes met
                nothing said which ink was whose. The tints are the ghosts'
                own, quiet and unlike the pens, so the pens still mean what
                they meant. */}
            {blob ? (
              <path
                d={smoothClosedPath(blob.map(screen))}
                fill={f.ground ?? GHOST_GROUNDS[i % GHOST_GROUNDS.length]}
                fillOpacity={openFiled === f.intentId || suggestion ? 0.16 : 0.09}
                stroke={suggestion ? f.color : "none"}
                strokeOpacity={0.35}
                strokeWidth={1.5}
                strokeDasharray="4 6"
              />
            ) : null}
            {f.notes
              .filter((n) => n.from && !n.continues && n.inStroke === undefined)
              .map((n) => (
                <path
                  key={`lead-${n.id}`}
                  d={leaderPath(screen(n.from!), screen(n))}
                  fill="none"
                  stroke={n.color ?? f.color}
                  strokeWidth={1.5}
                  strokeOpacity={0.25}
                  strokeDasharray="6 5"
                  strokeLinecap="round"
                />
              ))}
            {f.marks.map((m, i) =>
              m.points.length > 1 ? (
                <polyline
                  key={i}
                  points={m.points.map(screen).map((pt) => `${pt.x},${pt.y}`).join(" ")}
                  fill="none"
                  stroke={m.color}
                  strokeWidth={2}
                  strokeOpacity={0.22}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeDasharray="6 5"
                />
              ) : null,
            )}
          </g>
        ))}

        {/* Ghost nodes: what the agent says it is about to add, drawn where
            it will go. Grey and dotted while planned; the one being worked on
            marches in the remark's own colour; gone once the real thing has
            landed. */}
        {ghosts.flatMap(({ f, placed }) =>
          placed.map((it) => {
            const place = it.place!;
            const tl = screen({ x: place.x, y: place.y });
            const w = (place.width ?? GHOST_W) * viewport.zoom;
            const h = (place.height ?? GHOST_H) * viewport.zoom;
            const live = it.state === "active";
            return (
              <rect
                key={`gn-${it.id}`}
                data-testid="comment-lasso-ghost-node"
                data-state={it.state ?? "planned"}
                x={tl.x}
                y={tl.y}
                width={w}
                height={h}
                rx={8}
                fill={live ? f.color : "rgb(115,115,115)"}
                fillOpacity={live ? 0.06 : 0.04}
                stroke={live ? f.color : "rgb(140,140,140)"}
                strokeWidth={live ? 3 : 2.5}
                strokeDasharray={live ? "10 8" : "3 7"}
                strokeLinecap="round"
                style={live ? { animation: "anchor-ghost-march 1.4s linear infinite" } : undefined}
              />
            );
          }),
        )}

        {/* What a proposal would do, drawn where it would do it: the edges
            it adds or removes, and the outline of every card it touches. */}
        {ghosts.flatMap(({ f, preview }) => {
          if (!preview) return [];
          const edgeLines = preview.edges.map((e) => {
            const a = previewCentre(e.source, preview, storeNodes);
            const b = previewCentre(e.target, preview, storeNodes);
            if (!a || !b) return null;
            const sa = screen(a);
            const sb = screen(b);
            return (
              <line
                key={`pe-${f.intentId}-${e.id}`}
                data-testid="comment-lasso-preview-edge"
                x1={sa.x}
                y1={sa.y}
                x2={sb.x}
                y2={sb.y}
                stroke={e.kind === "removed" ? "rgb(220,38,38)" : f.color}
                strokeWidth={2.5}
                strokeDasharray="8 6"
                strokeOpacity={0.8}
              />
            );
          });
          const cardOutlines = preview.nodes.map((n) => {
            const tl = screen({ x: n.x, y: n.y });
            return (
              <rect
                key={`pn-${f.intentId}-${n.id}`}
                x={tl.x}
                y={tl.y}
                width={n.width * viewport.zoom}
                height={n.height * viewport.zoom}
                rx={8}
                fill={n.kind === "removed" ? "rgb(220,38,38)" : f.color}
                fillOpacity={n.kind === "removed" ? 0.05 : 0.08}
                stroke={n.kind === "removed" ? "rgb(220,38,38)" : f.color}
                strokeWidth={3}
                strokeDasharray="10 8"
                strokeLinecap="round"
                style={{ animation: "anchor-ghost-march 1.4s linear infinite" }}
              />
            );
          });
          return [...edgeLines, ...cardOutlines];
        })}

        {/* Remarks set aside: on their own ground, faint, waiting for a
            tap. Unsent, so the ground is outlined rather than the ink
            faded to a ghost's. */}
        {shelf.map((st) => {
          const b = blobOf(st);
          return (
            <g key={`shelf-${st.id}`} data-testid="comment-lasso-shelved">
              {b ? (
                <path
                  d={smoothClosedPath(b.map(screen))}
                  fill={st.ground}
                  fillOpacity={hoverShelf === st.id ? 0.2 : 0.12}
                  stroke={st.ground}
                  strokeOpacity={hoverShelf === st.id ? 0.9 : 0.6}
                  strokeWidth={1.5}
                  strokeDasharray="3 6"
                  strokeLinecap="round"
                />
              ) : null}
              {st.marks.map((m, i) =>
                m.points.length > 1 ? (
                  <polyline
                    key={i}
                    points={m.points.map(screen).map((pt) => `${pt.x},${pt.y}`).join(" ")}
                    fill="none"
                    stroke={m.color}
                    strokeWidth={2}
                    strokeOpacity={0.35}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                ) : null,
              )}
              {st.notes
                .filter((n) => n.from && !n.continues && n.inStroke === undefined)
                .map((n) => (
                  <path
                    key={`lead-${n.id}`}
                    d={leaderPath(screen(n.from!), screen(n))}
                    fill="none"
                    stroke={n.color ?? INK}
                    strokeWidth={1.5}
                    strokeOpacity={0.35}
                    strokeDasharray="6 5"
                    strokeLinecap="round"
                  />
                ))}
            </g>
          );
        })}

        {/* Leaders: scaffolding rather than something the reader said, so
            fainter than the marks. */}
        {notes.map((n) => {
          const origin = lineFrom(n);
          if (!origin || n.continues) return null;
          const a = screen(origin);
          const b = screen(notePos(n));
          const place = calledOut.get(n.id);
          // An offered leader arrives horizontally, the way a drawing's
          // callouts do, so the words read as a line of text rather than as
          // the end of a diagonal. A ring's leader too: it used to run
          // straight and turn the words to its angle, which for a ring that
          // could only be left upward stood the words on end.
          const d = leaderPath(a, b, place ? "level" : "chord");
          return (
            <path
              key={`lead-${n.id}`}
              data-testid="comment-lasso-leader"
              d={d}
              fill="none"
              strokeWidth={2}
              strokeOpacity={n.offered && !n.text.trim() ? 0.4 : 0.7}
              strokeDasharray="7 5"
              strokeLinecap="round"
              stroke={n.color ?? INK}
            />
          );
        })}

        {/* What the line would join if it were let go now. Drawn differently
            from "what the stroke caught": that one says which cards a remark
            is about, this one says a connection is about to be made. */}
        {dropOn
          ? boxes
              .filter((b) => b.id === dropOn)
              .map((b) => {
                const tl = screen({ x: b.x, y: b.y });
                const br = screen({ x: b.x + b.width, y: b.y + b.height });
                return (
                  <rect
                    key={`drop-${b.id}`}
                    data-testid="comment-lasso-drop-target"
                    x={tl.x - 5}
                    y={tl.y - 5}
                    width={Math.max(0, br.x - tl.x) + 10}
                    height={Math.max(0, br.y - tl.y) + 10}
                    rx={8}
                    fill={ink}
                    fillOpacity={0.12}
                    stroke={ink}
                    strokeWidth={3.5}
                    strokeDasharray="10 6"
                  />
                );
              })
          : null}

        {/* What the stroke caught, in the pen of the stroke that caught it.
            Colouring it with the pen in hand recoloured every caught card
            the moment a second pen was picked up, which read as the remark
            changing under the reader. A card added by cmd-click, with no
            stroke to take a pen from, takes the pen in hand. */}
        {boxes
          .filter((b) => ids.includes(b.id))
          .map((b) => {
            const tl = screen({ x: b.x, y: b.y });
            const br = screen({ x: b.x + b.width, y: b.y + b.height });
            const by = marks.find((m) => lassoHits(m.points, [b]).length > 0)?.color ?? ink;
            return (
              <rect
                key={b.id}
                x={tl.x - 3}
                y={tl.y - 3}
                width={Math.max(0, br.x - tl.x) + 6}
                height={Math.max(0, br.y - tl.y) + 6}
                rx={6}
                fill={by}
                fillOpacity={0.1}
                stroke={by}
                strokeWidth={2}
              />
            );
          })}

        {paths.map((path, i) => {
          if (path.length < 2) return null;
          // Picked out: pressed harder and lifted off the page. A mark the
          // reader has hold of should look different from one they have not
          // touched, before they go looking for the handles to be sure.
          const chosen = selected.strokes.includes(i);
          return (
            <polyline
              key={i}
              data-selected={chosen ? "" : undefined}
              points={path.map((pt) => `${pt.x},${pt.y}`).join(" ")}
              // Translucent and laid over the design, so the layer reads as
              // something on top of the work rather than part of it.
              fill={isLoop(all[i]!) ? (marks[i]?.color ?? ink) : "none"}
              fillOpacity={0.07}
              stroke={marks[i]?.color ?? ink}
              strokeWidth={chosen ? 4 : 2.5}
              strokeOpacity={chosen || hoveredStroke === i ? 1 : 0.85}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray={isLoop(all[i]!) ? undefined : "6 4"}
              style={
                chosen
                  ? { filter: "drop-shadow(0 2px 3px rgba(76, 29, 149, 0.45))" }
                  : undefined
              }
            />
          );
        })}
      </svg>

      <div
        ref={surfaceRef}
        data-testid="comment-lasso-surface"
        data-lifted={lifted ? "" : undefined}
        // A hand over the ink of a drawn shape, since pressing there takes
        // hold of it; the crosshair everywhere else, drawing.
        className={`absolute inset-0 z-20 ${
          lifted ? "pointer-events-none" : hoveredStroke !== null ? "cursor-grab" : "cursor-crosshair"
        }`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onClick={onClick as unknown as React.MouseEventHandler}
        onDoubleClick={onDoubleClick as unknown as React.MouseEventHandler}
      />

      {/* The comments. No box, no border: a felt pen on the page rather than
          another card someone added. A note written inside a drawn shape takes
          that shape's size, so the box you drew is the thing you wrote in. */}
      {notes.map((n) => {
        const host = n.inStroke !== undefined ? strokes[n.inStroke] : undefined;
        const bounds = host ? strokeBounds(host) : null;
        const inset = bounds ? Math.min(HOST_INSET_PX, bounds.width / 6) : 0;
        const pos = notePos(n);
        const at = screen(bounds ? { x: bounds.x + inset, y: bounds.y + inset } : pos);
        const zoom = viewport.zoom;
        const size = bounds
          ? {
              width: Math.max(20, (bounds.width - inset * 2) * zoom),
              height: Math.max(20, (bounds.height - inset * 2) * zoom),
            }
          : { width: NOTE_W * zoom, height: NOTE_H * zoom };
        // Words flow away from the line that brought them here, never back
        // over it: a leader drawn leftward hangs its text from the right edge,
        // one drawn upward sits the text on its bottom.
        // A note written inside a drawn shape is the shape's label: centred
        // both ways, growing downward rather than clipping.
        if (bounds) {
          return (
            <HostedNote
              key={n.id}
              value={n.text}
              offered={Boolean(n.offered) && !n.text.trim()}
              left={at.x}
              top={at.y}
              width={size.width}
              height={size.height}
              fontSize={NOTE_FONT_PX * zoom}
              onChange={(v) =>
                setNotes((prev) =>
                  prev.map((m) => (m.id === n.id ? { ...m, text: v, offered: false } : m)),
                )
              }
              editing={editing === n.id}
              color={n.color ?? INK}
              onBlur={() => {
                setNotes((prev) => prev.filter((m) => m.id !== n.id || m.text.trim()));
                setEditing((cur) => (cur === n.id ? null : cur));
              }}
              onCommit={() => setEditing(null)}
              onGrow={(px) => growHost(n.inStroke!, px / zoom + inset * 2)}
            />
          );
        }
        // Words flow away from the line that brought them here, never back
        // over it: a leader drawn leftward hangs its text from the right edge,
        // one drawn upward sits the text on its bottom.
        // The words carry on the leader: same lean, centred on its end. A note
        // written without one sits level, since there is no line to continue.
        const origin = lineFrom(n);
        const place = calledOut.get(n.id);
        // Called out: level, and hanging off whichever edge it left by, so
        // the words run away from the card rather than back across it.
        const lean = place
          ? { deg: 0, flip: place.side === "left" }
          : origin && n.continues
            ? leaderAngle(origin, pos)
            : { deg: 0, flip: Boolean(origin) && pos.x < origin!.x };
        return (
          <FloatingNote
            key={n.id}
            value={n.text}
            offered={Boolean(n.offered) && !n.text.trim()}
            editing={editing === n.id}
            at={at}
            width={size.width}
            deg={lean.deg}
            flip={lean.flip}
            gap={NOTE_LEAD_GAP_PX * zoom}
            color={n.color ?? INK}
            fontSize={NOTE_FONT_PX * zoom}
            onChange={(v) =>
              setNotes((prev) =>
                prev.map((m) => (m.id === n.id ? { ...m, text: v, offered: false } : m)),
              )
            }
            onBlur={() => {
              // An empty note is a mis-click, or an offer nobody took.
              setNotes((prev) => prev.filter((m) => m.id !== n.id || m.text.trim()));
              setEditing((cur) => (cur === n.id ? null : cur));
            }}
            onCommit={() => setEditing(null)}
            onGrab={(e) => {
              setSelected(NOTHING_SELECTED);
              setActiveLabel(n.id);
              labelDrag.current = { id: n.id, start: toFlow(e), from: notePos(n) };
              e.currentTarget.setPointerCapture(e.pointerId);
            }}
            onDrag={(e) => {
              const d = labelDrag.current;
              if (!d || d.id !== n.id) return;
              const p = toFlow(e);
              moveLabel(n.id, {
                x: d.from.x + (p.x - d.start.x),
                y: d.from.y + (p.y - d.start.y),
              });
            }}
            onDrop={() => {
              labelDrag.current = null;
            }}
            onEdit={() => setEditing(n.id)}
            active={activeLabel === n.id}
            onRemove={() => removeLabel(n.id)}
          />
        );
      })}

      {/* The pens, as a bar of slots along the bottom.

          A row of squares with the number on each, the one in hand raised and
          lit. Borrowed shamelessly from a game that solved this: the reader
          learns it at a glance, reaches for a key rather than a menu, and the
          bar says what 1 through 9 will do without being asked. */}
      <div
        data-testid="comment-lasso-hotbar"
        // Where the tool rail stands, in its place: the rail steps aside
        // while marking up and this dark bar is the mode. Its first tile is
        // the mark-up tool itself, lit, and pressing it puts the pen down.
        className="pointer-events-auto absolute left-3 top-1/2 z-40 flex -translate-y-1/2 flex-col items-center gap-1 rounded-xl border border-neutral-700/40 bg-neutral-900/85 px-1 py-1.5 shadow-lg backdrop-blur transition-opacity"
        style={lifted ? { opacity: 0.45 } : undefined}
        onPointerDown={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          data-testid="comment-lasso-exit"
          aria-label="Put the pen down"
          aria-pressed
          title="mark up (i) — press to put the pen down"
          onClick={() => onExit?.()}
          className="relative grid h-9 w-9 place-items-center rounded-lg border border-violet-400/70 bg-violet-500/25 text-violet-100 transition hover:bg-violet-500/40"
        >
          <WandSparkles size={16} strokeWidth={1.75} aria-hidden />
          <span className="pointer-events-none absolute bottom-0 right-0.5 text-[8px] leading-none text-white/60" aria-hidden>
            I
          </span>
        </button>
        <button
          type="button"
          data-testid="comment-lasso-new"
          aria-label="New remark"
          title="new remark (n) — set this one aside, unsent, and start another"
          onClick={() => newStack()}
          className="relative grid h-9 w-9 place-items-center rounded-lg border border-transparent text-white/80 transition hover:border-white/30 hover:bg-white/10"
        >
          <Plus size={16} strokeWidth={1.75} aria-hidden />
          <span className="pointer-events-none absolute bottom-0 right-0.5 text-[8px] leading-none text-white/60" aria-hidden>
            N
          </span>
        </button>
        {/* Every remark on the board, the one in hand lit: set one aside with
            N and it stays here as a tile, one press away. Ordered by ground,
            which a remark keeps for life, so a tile never moves when another
            is picked up. */}
        {shelf.length > 0
          ? [{ id: null as string | null, ground, marks, notes }, ...shelf]
              .sort((a, b) => GHOST_GROUNDS.indexOf(a.ground) - GHOST_GROUNDS.indexOf(b.ground))
              .map((st) => {
                const live = st.id === null;
                const words = st.notes.map((n) => n.text.trim()).filter(Boolean).join(" · ");
                const pen = st.marks[0]?.color;
                return (
                  <button
                    key={st.id ?? "live"}
                    type="button"
                    data-testid="comment-lasso-stack"
                    data-live={live ? "" : undefined}
                    aria-pressed={live}
                    aria-label={live ? "The remark in hand" : `Go on with: ${words || "unwritten remark"}`}
                    title={`${live ? "in hand" : "set aside, press to go on with it"}${words ? `: ${words.slice(0, 60)}` : ""}`}
                    onClick={() => {
                      if (live) {
                        reveal({ marks: marksRef.current, notes: notesRef.current, ids });
                        return;
                      }
                      const target = shelfRef.current.find((x) => x.id === st.id);
                      if (target) reveal(target);
                      switchTo(st.id!);
                    }}
                    className="relative grid h-7 w-7 place-items-center rounded-md transition"
                    style={{
                      background: st.ground,
                      opacity: live ? 1 : 0.7,
                      outline: live ? "2px solid rgba(255,255,255,0.9)" : "1px solid rgba(255,255,255,0.25)",
                      outlineOffset: live ? "1px" : "-1px",
                    }}
                  >
                    {pen ? (
                      <span className="h-2 w-2 rounded-full" style={{ background: pen, boxShadow: "0 0 0 1px rgba(0,0,0,0.25)" }} />
                    ) : null}
                  </button>
                );
              })
          : null}
        <div className="my-1 h-px w-7 bg-white/20" aria-hidden />
        {PALETTE.map((pen) => {
          const inHand = pen.ink === ink;
          return (
            <button
              key={pen.key}
              type="button"
              data-testid="comment-lasso-pen"
              data-in-hand={inHand ? "" : undefined}
              aria-label={`${pen.name} pen`}
              aria-pressed={inHand}
              title={`${pen.name} (${pen.key})`}
              onClick={() => {
                setInk(pen.ink);
                recolourSelected(pen.ink);
              }}
              className="relative grid h-8 w-8 place-items-center rounded transition"
              style={{
                background: inHand ? "rgba(255,255,255,0.18)" : "rgba(255,255,255,0.05)",
                outline: inHand ? "2px solid rgba(255,255,255,0.85)" : "none",
                outlineOffset: "-2px",
                transform: inHand ? "translateY(-2px)" : undefined,
              }}
            >
              <span
                className="h-4 w-4 rounded-sm"
                style={{ background: pen.ink, boxShadow: "0 1px 2px rgba(0,0,0,0.45)" }}
              />
              <span className="absolute bottom-0 right-0.5 text-[8px] leading-none text-white/70">
                {pen.key}
              </span>
            </button>
          );
        })}
      </div>

      {/* Set-aside remarks' words, as ink. */}
      {shelf.flatMap((st) =>
        st.notes.map((n) => (
          <FaintNote
            key={`${st.id}-${n.id}`}
            note={n}
            strokes={st.marks.map((m) => m.points)}
            screen={screen}
            zoom={viewport.zoom}
          />
        )),
      )}

      {/* Filed remarks' words, as ink. */}
      {filed.flatMap((f) =>
        f.notes.map((n) => (
          <FaintNote
            key={`${f.intentId}-${n.id}`}
            note={n}
            strokes={f.marks.map((m) => m.points)}
            screen={screen}
            zoom={viewport.zoom}
          />
        )),
      )}

      {/* The previewed cards, as they will read: label and rows. Laid over
          the real card for an update, so what the reader sees is the result;
          struck through for a removal. Approve is beside them, not beside a
          paragraph about them. */}
      {ghosts.flatMap(({ f, preview }) =>
        (preview?.nodes ?? []).map((n) => {
          const tl = screen({ x: n.x, y: n.y });
          const w = n.width * viewport.zoom;
          const h = n.height * viewport.zoom;
          const removed = n.kind === "removed";
          return (
            <div
              key={`pv-${f.intentId}-${n.id}`}
              data-testid="comment-lasso-preview-node"
              data-kind={n.kind}
              className="pointer-events-none absolute z-30 overflow-hidden rounded-lg bg-white/90 px-2 py-1.5"
              style={{ left: tl.x, top: tl.y, width: w, minHeight: h, fontSize: 12 * viewport.zoom }}
            >
              <div className="text-[0.8em] uppercase tracking-wide" style={{ color: f.color }}>
                {n.kind === "added" ? "will add" : n.kind === "updated" ? "will become" : "will remove"}
              </div>
              <div
                className={`truncate font-medium text-neutral-800 ${removed ? "line-through" : ""}`}
              >
                {n.label}
              </div>
              {n.rows.length > 0 ? (
                <table className="mt-1 w-full">
                  <tbody>
                    {n.rows.map((r, i) => (
                      <tr key={i} className={`border-t border-neutral-100 ${removed ? "line-through" : ""}`}>
                        <td className="py-0.5 pr-2 text-neutral-500">{r.key}</td>
                        <td className="py-0.5 text-neutral-800">{r.value}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : null}
              {n.before && n.before.rows.length !== n.rows.length ? (
                <div className="mt-1 text-[0.8em] text-neutral-400">
                  was {n.before.rows.length} row{n.before.rows.length === 1 ? "" : "s"}
                </div>
              ) : null}
            </div>
          );
        }),
      )}

      {/* Ghost nodes' words: the title in the middle, the status beneath. */}
      {ghosts.flatMap(({ f, placed }) =>
        placed.map((it) => {
          const place = it.place!;
          const tl = screen({ x: place.x, y: place.y });
          const w = (place.width ?? GHOST_W) * viewport.zoom;
          const h = (place.height ?? GHOST_H) * viewport.zoom;
          const { title, status } = splitGhostText(it.text);
          const live = it.state === "active";
          return (
            <div
              key={`gt-${it.id}`}
              className="pointer-events-none absolute z-30 flex flex-col items-center justify-center px-2 text-center"
              style={{ left: tl.x, top: tl.y, width: w, height: h }}
            >
              <div
                className="text-[12px] font-medium leading-tight"
                style={{ color: live ? f.color : "rgb(115,115,115)" }}
              >
                {title}
              </div>
              {status ? (
                <div className="mt-0.5 text-[10px] leading-tight text-neutral-500">{status}</div>
              ) : null}
            </div>
          );
        }),
      )}

      {/* Under each ghost: the agent's latest word, any open question, and
          the verdict buttons once there is something to judge. This is where
          the reader looks for the outcome, because it is where they asked. */}
      {ghosts.map(({ f, blob, status, questions, suggestion, applied }) => {
        if (!blob) return null;
        const c = loopCentre(blob);
        const foot = screen(exitLoop(blob, c, { x: c.x, y: c.y + 1e5 }));
        const pending = f.intent?.status !== "resolved";
        return (
          <div
            key={`gs-${f.intentId}`}
            data-testid="comment-lasso-ghost-status"
            className="absolute z-30 flex w-64 -translate-x-1/2 flex-col items-center gap-1"
            style={{ left: foot.x, top: foot.y + 6 }}
          >
            {status ? (
              <div className="flex items-center gap-1.5 text-[11px] text-neutral-600">
                {pending ? (
                  <span
                    className="inline-block h-1.5 w-1.5 animate-pulse rounded-full"
                    style={{ background: f.color }}
                  />
                ) : null}
                <span>{status.text}</span>
              </div>
            ) : pending && !suggestion && !applied ? (
              <div className="text-[11px] text-neutral-400">sent · waiting for the agent</div>
            ) : null}

            {questions.map((q) => (
              <div
                key={q.id}
                data-testid="comment-lasso-ghost-question"
                className="pointer-events-auto w-full rounded-md border bg-white p-2 shadow-md"
                style={{ borderColor: f.color }}
                onPointerDown={(e) => e.stopPropagation()}
              >
                <div className="text-[11px] text-neutral-800">{q.text}</div>
                {/* Answers the agent offered: one press each. Typing is
                    still there underneath, for the answer it did not think
                    of. Less to say is less to get wrong. */}
                {q.options && q.options.length > 0 ? (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {q.options.map((opt) => (
                      <button
                        key={opt}
                        type="button"
                        data-testid="comment-lasso-option"
                        className="rounded-full border px-2 py-0.5 text-[11px] hover:bg-neutral-50"
                        style={{ borderColor: f.color, color: f.color }}
                        onClick={() => void intents.answer(f.intentId, q.id, opt)}
                      >
                        {opt}
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="mt-1 flex gap-1">
                  <input
                    value={answering?.item === q.id ? answering.text : ""}
                    onChange={(e) => setAnswering({ item: q.id, text: e.target.value })}
                    onKeyDown={(e) => {
                      e.stopPropagation();
                      if (e.key === "Enter" && answering?.item === q.id && answering.text.trim()) {
                        void intents.answer(f.intentId, q.id, answering.text.trim());
                        setAnswering(null);
                      }
                    }}
                    placeholder="answer"
                    className="min-w-0 flex-1 rounded border border-neutral-300 px-1.5 py-0.5 text-[11px] outline-none focus:border-neutral-500"
                  />
                  <button
                    type="button"
                    className="rounded px-2 py-0.5 text-[11px] text-white"
                    style={{ background: f.color }}
                    onClick={() => {
                      if (answering?.item === q.id && answering.text.trim()) {
                        void intents.answer(f.intentId, q.id, answering.text.trim());
                        setAnswering(null);
                      }
                    }}
                  >
                    answer
                  </button>
                </div>
              </div>
            ))}

            {applied ? (
              <div
                data-testid="comment-lasso-ghost-applied"
                className="pointer-events-auto w-full rounded-md border bg-white p-2 shadow-md"
                style={{ borderColor: f.color }}
                onPointerDown={(e) => e.stopPropagation()}
              >
                {/* The change is on the canvas. The only question is whether it
                    stays, so that is the only question asked. */}
                <div className="text-[10px] uppercase tracking-wide" style={{ color: f.color }}>
                  done
                </div>
                <div className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-neutral-600">
                  {applied.text.split("\n")[0]}
                </div>
                <div className="mt-1.5 flex gap-1.5">
                  <button
                    type="button"
                    data-testid="comment-lasso-keep"
                    className="rounded bg-emerald-600 px-2 py-0.5 text-[11px] text-white hover:bg-emerald-700"
                    onClick={() => {
                      const next = new Set(kept).add(applied.id);
                      setKept(next);
                      void settle(f.intentId, next);
                    }}
                  >
                    keep
                  </button>
                  <button
                    type="button"
                    data-testid="comment-lasso-revert"
                    className="rounded border border-rose-300 px-2 py-0.5 text-[11px] text-rose-700 hover:bg-rose-50"
                    onClick={() =>
                      void intents.revert(f.intentId, applied.id).then(() => settle(f.intentId, kept))
                    }
                  >
                    put it back
                  </button>
                </div>
                <ReplyLine
                  color={f.color}
                  onSend={(text) => void intents.addItem(f.intentId, { type: "message", text })}
                />
              </div>
            ) : null}

            {suggestion ? (
              <div
                data-testid="comment-lasso-ghost-verdict"
                className="pointer-events-auto w-full rounded-md border bg-white p-2 shadow-md"
                style={{ borderColor: f.color }}
                onPointerDown={(e) => e.stopPropagation()}
              >
                <div className="text-[10px] uppercase tracking-wide" style={{ color: f.color }}>
                  proposal
                </div>
                {/* One line. The preview above IS the proposal; a paragraph
                    describing what the reader can see is noise. */}
                <div className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-neutral-600">
                  {suggestion.text.split("\n")[0]}
                </div>
                <div className="mt-1.5 flex gap-1.5">
                  <button
                    type="button"
                    data-testid="comment-lasso-approve"
                    className="rounded bg-emerald-600 px-2 py-0.5 text-[11px] text-white hover:bg-emerald-700"
                    onClick={() => void intents.apply(f.intentId, suggestion.id)}
                  >
                    approve
                  </button>
                  <button
                    type="button"
                    data-testid="comment-lasso-decline"
                    className="rounded border border-rose-300 px-2 py-0.5 text-[11px] text-rose-700 hover:bg-rose-50"
                    onClick={() => void intents.decline(f.intentId, suggestion.id)}
                  >
                    decline
                  </button>
                  {/* Neither: draw on the preview and send that back. The
                      marks and words in hand become a message on this
                      thread, with their structure, and the proposal stays
                      pending for the agent to revise. */}
                  {written ? (
                    <button
                      type="button"
                      data-testid="comment-lasso-feedback"
                      className="rounded border px-2 py-0.5 text-[11px] hover:bg-neutral-50"
                      style={{ borderColor: f.color, color: f.color }}
                      onClick={() => {
                        const drawn = [describeSketch(reading), describeCuts(cutsReading)]
                          .filter(Boolean)
                          .join("\n");
                        void intents.addItem(f.intentId, {
                          type: "message",
                          text: drawn ? `${written}\n\n--- drawn ---\n${drawn}` : written,
                        });
                        reset();
                      }}
                    >
                      send my marks as feedback
                    </button>
                  ) : null}
                </div>
                <ReplyLine
                  color={f.color}
                  onSend={(text) => void intents.addItem(f.intentId, { type: "message", text })}
                />
              </div>
            ) : null}
          </div>
        );
      })}

      {/* The rubber band, while it is being dragged. */}
      {marquee
        ? (() => {
            const r = rectFrom(marquee.a, marquee.b);
            const tl = screen({ x: r.x, y: r.y });
            return (
              <div
                data-testid="comment-lasso-marquee"
                className="pointer-events-none absolute z-40 rounded-sm border border-violet-400 bg-violet-400/10"
                style={{
                  left: tl.x,
                  top: tl.y,
                  width: r.width * viewport.zoom,
                  height: r.height * viewport.zoom,
                }}
              />
            );
          })()
        : null}

      {/* What has been picked out, and what can be done to it.

          Handles appear here and nowhere else: on the marks the reader has
          actually chosen. They used to follow the pointer, which turned every
          shape it crossed into eight live targets standing between the reader
          and the next line they wanted to draw.

          One mark on its own wears its controls ON the ink -- a tab to pull it
          by, a cross to erase it, a square in the bottom corner to size it --
          each shrink-wrapped onto the nearest point of the stroke, the way the
          erase cross already was. Several at once get a box around the lot,
          because there is no single line for them to hang off. */}
      {lone !== null && strokes[lone]
        ? (() => {
            const stroke = strokes[lone]!;
            const b = strokeBounds(stroke);
            const top = screen(nearestOnStroke(stroke, { x: b.x + b.width, y: b.y }));
            const bottom = screen(
              nearestOnStroke(stroke, { x: b.x + b.width, y: b.y + b.height }),
            );
            const only: Selection = { strokes: [lone], notes: [] };
            // The controls are drawn with the mark's own pen, so a red mark's
            // handles are red. They belong to that mark, not to the toolbar.
            const pen = marks[lone]?.color ?? INK;
            return (
              <div key="lone" data-testid="comment-lasso-selection">
                <button
                  type="button"
                  data-testid="comment-lasso-erase-selection"
                  aria-label="Delete this mark"
                  className="absolute z-40 grid place-items-center rounded-full transition hover:text-rose-600"
                  style={{
                    color: pen,
                    left: top.x - ERASE_PX / 2,
                    top: top.y - ERASE_PX / 2,
                    width: ERASE_PX,
                    height: ERASE_PX,
                    cursor: "pointer",
                  }}
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={(e) => {
                    e.stopPropagation();
                    removeSelected();
                  }}
                >
                  <SketchCross />
                </button>
                <div
                  data-testid="comment-lasso-handle"
                  role="presentation"
                  title="Drag to resize"
                  className="absolute z-40"
                  style={{
                    color: pen,
                    left: bottom.x - HANDLE_PX / 2,
                    top: bottom.y - HANDLE_PX / 2,
                    width: HANDLE_PX,
                    height: HANDLE_PX,
                    cursor: "nwse-resize",
                  }}
                  onPointerDown={startGroupDrag("resize", { x: 1, y: 1 }, only)}
                  onPointerMove={onGroupDragMove}
                  onPointerUp={endGroupDrag}
                  onPointerCancel={endGroupDrag}
                >
                  <SketchSquare />
                </div>
              </div>
            );
          })()
        : picked
          ? (() => {
              const tl = screen({ x: picked.x, y: picked.y });
              const w = picked.width * viewport.zoom;
              const h = picked.height * viewport.zoom;
              return (
                <div key="selection" data-testid="comment-lasso-selection">
                  <div
                    className="pointer-events-none absolute z-40 rounded-sm border border-dashed border-violet-400"
                    style={{ left: tl.x, top: tl.y, width: w, height: h }}
                  />
                  <button
                    type="button"
                    data-testid="comment-lasso-erase-selection"
                    aria-label={`Delete ${selected.strokes.length + selected.notes.length} marks`}
                    className="absolute z-40 grid place-items-center rounded-full text-violet-600 transition hover:text-rose-600"
                    style={{
                      left: tl.x + w - ERASE_PX / 2,
                      top: tl.y - ERASE_PX / 2,
                      width: ERASE_PX,
                      height: ERASE_PX,
                      cursor: "pointer",
                    }}
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={(e) => {
                      e.stopPropagation();
                      removeSelected();
                    }}
                  >
                    <SketchCross />
                  </button>
                  {CORNERS.map((corner) => {
                    const at = { x: tl.x + corner.x * w, y: tl.y + corner.y * h };
                    return (
                      <div
                        key={`h${corner.x}${corner.y}`}
                        data-testid="comment-lasso-handle"
                        role="presentation"
                        className="absolute z-40 text-violet-500"
                        style={{
                          left: at.x - HANDLE_PX / 2,
                          top: at.y - HANDLE_PX / 2,
                          width: HANDLE_PX,
                          height: HANDLE_PX,
                          cursor: corner.x === corner.y ? "nwse-resize" : "nesw-resize",
                        }}
                        onPointerDown={startGroupDrag("resize", corner)}
                        onPointerMove={onGroupDragMove}
                        onPointerUp={endGroupDrag}
                        onPointerCancel={endGroupDrag}
                      >
                        <SketchSquare />
                      </div>
                    );
                  })}
                </div>
              );
            })()
          : null}

      {/* Picking a stroke back up: a × on the mark while the pointer is on it.
          A click and a menu was ceremony for what is almost always "that one
          was a mistake".

          It aims at the top-right corner of the stroke's box and is then
          pulled in onto the ink. Left at the corner it sat in open canvas --
          on a wide ring, a hand's travel away from anything the reader drew --
          and reaching for it crossed empty space, which took the pointer off
          the stroke and took the button with it. */}
      {hoveredStroke !== null && strokes[hoveredStroke] && lone !== hoveredStroke ? (() => {
        const stroke = strokes[hoveredStroke]!;
        const b = strokeBounds(stroke);
        const at = screen(nearestOnStroke(stroke, { x: b.x + b.width, y: b.y }));
        const bottom = screen(nearestOnStroke(stroke, { x: b.x + b.width, y: b.y + b.height }));
        const pen = marks[hoveredStroke]?.color ?? INK;
        const only: Selection = { strokes: [hoveredStroke], notes: [] };
        return (
          <>
            <button
              type="button"
              data-testid="comment-lasso-erase"
              aria-label="Delete this stroke"
              className="absolute z-40 grid place-items-center rounded-full transition hover:text-rose-600"
              style={{
                color: pen,
                left: at.x - ERASE_PX / 2,
                top: at.y - ERASE_PX / 2,
                width: ERASE_PX,
                height: ERASE_PX,
                cursor: "pointer",
              }}
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => removeStroke(hoveredStroke)}
            >
              <SketchCross />
            </button>
            {/* The resize handle as soon as the shape is under the hand, not
                after a click: the shape is already showing its × here, and
                a second press to earn the handle was a step nobody wanted. */}
            <div
              data-testid="comment-lasso-hover-handle"
              role="presentation"
              title="Drag to resize"
              className="absolute z-40"
              style={{
                color: pen,
                left: bottom.x - HANDLE_PX / 2,
                top: bottom.y - HANDLE_PX / 2,
                width: HANDLE_PX,
                height: HANDLE_PX,
                cursor: "nwse-resize",
              }}
              onPointerDown={startGroupDrag("resize", { x: 1, y: 1 }, only)}
              onPointerMove={onGroupDragMove}
              onPointerUp={endGroupDrag}
              onPointerCancel={endGroupDrag}
            >
              <SketchSquare />
            </div>
          </>
        );
      })() : null}

      {/* Queue it, under whatever the reader just wrote, so the confirmation
          is where their attention already is. */}
      {sayable ? (() => {
        // On the edge of the shape, down and to the right -- the corner a
        // reader's eye finishes on, and near enough to the marks to read as
        // "file THESE" rather than as another button on the page.
        const centre = remarkBlob ? loopCentre(remarkBlob) : null;
        const anchorPt =
          centre && remarkBlob
            ? screen(
                exitLoop(remarkBlob, centre, {
                  x: centre.x + 1e5,
                  y: centre.y + 1e5,
                }),
              )
            : screen({
                x: Math.min(...all.flat().map((p) => p.x)),
                y: Math.max(...all.flat().map((p) => p.y)),
              });
        return (
          <div
            className="absolute z-40 flex items-center gap-1"
            style={{ left: anchorPt.x, top: anchorPt.y }}
            onPointerDown={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              data-testid="comment-lasso-send"
              disabled={sending}
              className="cursor-pointer rounded-full bg-violet-600 px-3 py-1 text-[12px] text-white shadow-lg hover:bg-violet-700 disabled:cursor-default disabled:bg-neutral-400"
              onClick={() => void sendRemark()}
            >
              {sending ? "sending…" : "send to agent"}
              {ids.length > 0 ? ` · ${ids.length} node${ids.length === 1 ? "" : "s"}` : ""}
            </button>
            {/* The whole remark, gone: every mark and every word of it.
                Deleting a remark one stroke at a time is how a false start
                turns into five minutes. */}
            <button
              type="button"
              data-testid="comment-lasso-discard"
              title="discard this remark"
              className="grid h-6 w-6 cursor-pointer place-items-center rounded-full border border-neutral-300 bg-white text-[13px] leading-none text-neutral-500 shadow hover:border-rose-300 hover:text-rose-600"
              onClick={() => reset()}
            >
              ×
            </button>
          </div>
        );
      })() : null}

      <div
        ref={panelRef}
        data-testid="comment-lasso-readout"
        // Transparent to the pointer, buttons aside. It sits over the canvas,
        // and catching clicks made the whole strip under it a dead zone: a
        // ring drawn down there registered as nothing at all, with no sign of
        // why. Only the things meant to be pressed take the pointer back.
        // Out of the way by default, a thumb's width in from the bottom
        // right corner; carried anywhere by its title.
        className="pointer-events-none absolute z-30 w-[min(21rem,60vw)] rounded-lg border border-violet-300 bg-white/95 p-3 shadow-xl backdrop-blur"
        style={panelAt ? { left: panelAt.x, top: panelAt.y } : { right: PANEL_INSET_PX, bottom: PANEL_INSET_PX }}
      >
        <div
          className="pointer-events-auto flex cursor-move select-none items-baseline justify-between text-[11px]"
          data-testid="comment-lasso-readout-handle"
          onPointerDown={(e) => {
            e.stopPropagation();
            const panel = panelRef.current;
            const host = panel?.offsetParent as HTMLElement | null;
            if (!panel || !host) return;
            const pr = panel.getBoundingClientRect();
            const hr = host.getBoundingClientRect();
            panelDrag.current = {
              startX: e.clientX,
              startY: e.clientY,
              x: pr.left - hr.left,
              y: pr.top - hr.top,
            };
            e.currentTarget.setPointerCapture(e.pointerId);
          }}
          onPointerMove={(e) => {
            const d = panelDrag.current;
            if (!d) return;
            setPanelAt({ x: d.x + (e.clientX - d.startX), y: d.y + (e.clientY - d.startY) });
          }}
          onPointerUp={() => {
            panelDrag.current = null;
          }}
        >
          <span className="font-medium uppercase tracking-wide text-violet-700">
            Comment mode
          </span>
          <span className="text-neutral-500">
            {lifted
              ? "pen up · hover and click what is underneath · release space to draw"
              : dropOn
              ? "let go to join these two"
              : editing
              ? "enter when you have finished writing · shift+enter for a new row"
              : current
              ? looping
                ? "ring — taking what the area touches"
                : "line — taking what it crosses"
              : strokes.length > 0
                ? `${strokes.length} stroke${strokes.length > 1 ? "s" : ""} · keep drawing, or double-click to write`
                : "draw across or around things · double-click to write"}
          </span>
        </div>
        {cutsReading.length > 0 ? (
          <div className="mt-1 text-[11px] text-violet-700" data-testid="comment-lasso-cuts">
            {cutsReading.map((c) => (
              <div key={`${c.node}-${c.after}`}>
                cuts <b>{String(storeNodes[c.node]?.data?.label ?? c.node)}</b> after row{" "}
                <b>{c.after}</b>
              </div>
            ))}
          </div>
        ) : null}
        {strikesReading.length > 0 ? (
          <div className="mt-1 text-[11px] text-violet-700" data-testid="comment-lasso-strikes">
            {strikesReading.map((k) => (
              <div key={k.edge}>
                strikes out the link{" "}
                <b>{String(storeNodes[k.source]?.data?.label ?? k.source)}</b> →{" "}
                <b>{String(storeNodes[k.target]?.data?.label ?? k.target)}</b>
              </div>
            ))}
          </div>
        ) : null}
        {reading.nodes.length > 0 ? (
          <div className="mt-1 text-[11px] text-violet-700" data-testid="comment-lasso-reading">
            reads as <b>{reading.nodes.length}</b> shape
            {reading.nodes.length === 1 ? "" : "s"}
            {reading.edges.length > 0 ? (
              <>
                {" "}
                and <b>{reading.edges.length}</b> link
                {reading.edges.length === 1 ? "" : "s"}
              </>
            ) : null}
          </div>
        ) : null}
        <div className="mt-1 text-[11px] text-neutral-600">
          {ids.length === 0 ? (
            // A remark that catches nothing is not a mistake. Drawing on open
            // canvas is how you ask for something that is not there yet, and
            // refusing to file it left the whole sketch stranded on screen.
            <span className="text-neutral-400">
              {written ? "about nothing on the canvas yet" : "nothing selected yet"}
            </span>
          ) : (
            <span data-testid="comment-lasso-ids">
              <b>{ids.length}</b> selected: {ids.join(", ")}
            </span>
          )}
        </div>
        <div className="mt-1 text-[10px] text-neutral-400">
          cmd-click a node to add or remove it · shift-drag to pick out marks · n
          sets this remark aside and starts another · drag a line to move it,
          option-drag to pull it · hold space to lift the pen and look underneath
          · esc puts the pen down, the ink stays
          {shelf.length > 0
            ? ` · ${shelf.length} set aside: press its tile, or tap its ground, to go on with it`
            : ""}
        </div>


        {/* What has been sent and is still on the board: each one opens to
            its thread -- the ask, then everything the agent said and did,
            then the proposal -- in the order it happened. */}
        {filed.length > 0 ? (
          <div className="mt-2 border-t border-neutral-200 pt-2" data-testid="comment-lasso-filed">
            <div className="text-[11px] font-medium text-neutral-600">
              {filed.length} sent · on the board
            </div>
            <ul className="mt-1 space-y-0.5">
              {ghosts.map(({ f, items, suggestion, questions }) => {
                const open = openFiled === f.intentId;
                const pending = f.intent?.status !== "resolved";
                return (
                  <li key={f.intentId} className="text-[11px] text-neutral-600">
                    <button
                      type="button"
                      className="pointer-events-auto flex w-full items-baseline gap-2 text-left hover:text-neutral-900"
                      onClick={() => setOpenFiled(open ? null : f.intentId)}
                    >
                      <span
                        className="inline-block h-2 w-2 shrink-0 rounded-full"
                        style={{ background: f.color, opacity: pending ? 1 : 0.4 }}
                      />
                      <span className="truncate">{f.text.split("\n")[0]}</span>
                      <span className="shrink-0 text-neutral-400">
                        {suggestion
                          ? "proposal"
                          : questions.length > 0
                            ? "question"
                            : pending
                              ? `${items.length} step${items.length === 1 ? "" : "s"}`
                              : "done"}
                      </span>
                    </button>
                    {open ? (
                      <ol className="ml-4 mt-0.5 space-y-0.5 border-l border-neutral-200 pl-2">
                        <li className="text-neutral-500">you: {f.text}</li>
                        {items.map((it) => (
                          <li key={it.id} className="text-neutral-600">
                            <span className="text-neutral-400">
                              {it.author.kind === "human" ? "you" : it.author.label ?? it.author.kind}
                              {" · "}
                              {it.type}
                              {it.state ? ` · ${it.state}` : ""}
                              {": "}
                            </span>
                            {it.text}
                            {it.answer ? <span className="text-neutral-500"> → {it.answer}</span> : null}
                          </li>
                        ))}
                        {f.intent?.result ? (
                          <li className="text-emerald-700">
                            done: {String((f.intent.result as { action?: string }).action ?? "resolved")}
                          </li>
                        ) : null}
                      </ol>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  );
}
