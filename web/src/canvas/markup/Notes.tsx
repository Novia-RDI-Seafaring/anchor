import {
  leaderAngle,
  strokeBounds,
  type Point
} from "@/canvas/lasso";
import { type Note } from "@/stores/markupStore";
import { useEffect, useEffectEvent, useLayoutEffect, useRef, useState } from "react";
import { ERASE_PX, HOST_INSET_PX, INK, NOTE_FONT_PX, NOTE_LEAD_GAP_PX, NOTE_W } from "./constants";
import { SketchCross } from "./InkIcons";

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
 * rather than clipping  -  at that point the reader has stopped drawing a
 * shape and started writing in a box, and losing the end of a sentence to a
 * border they sketched by hand would be a poor trade.
 */
export function HostedNote({
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
  // Re-measure for text and geometry; use the current host callback inside the effect.
  const grow = useEffectEvent(onGrow);

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
    if (text > height + 1) grow(text);
    // Effect events always use the latest callback and are not effect dependencies.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      placeholder={offered ? "write\u2026" : "write"}
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
 * A comment written on open canvas, at the end of a leader or where it was
 * asked for. No box and no border: felt pen on the page, rather than another
 * card someone added to the design.
 */
export function FloatingNote({
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
          placeholder={offered ? "write\u2026" : "write"}
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
 * A queued remark's words, as ink rather than as a field.
 *
 * Already said, so it is faint and cannot be typed in -- but it is still
 * there. Fading the strokes and dropping the text left the pile as a set of
 * anonymous scribbles, and a mark with no words says nothing about why it was
 * drawn, which is the whole content of the remark.
 */
export function FaintNote({
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
