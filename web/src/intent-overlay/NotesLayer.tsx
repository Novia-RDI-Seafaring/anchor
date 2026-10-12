import {
  leaderAngle,
  strokeBounds
} from "./lasso";
import { NOTHING_SELECTED } from "./markupStore";
import { HOST_INSET_PX, INK, NOTE_FONT_PX, NOTE_H, NOTE_LEAD_GAP_PX, NOTE_W } from "./constants";
import { FaintNote, FloatingNote, HostedNote } from "./Notes";
import type { MarkupModel } from "./types";
import { appendMarkup, captureMarkup } from "./clipboard";

export function LiveNotes({ model }: { model: Pick<MarkupModel, "notes" | "strokes" | "notePos" | "screen" | "viewport" | "setNotes" | "editing" | "markupStore" | "setEditing" | "growHost" | "lineFrom" | "calledOut" | "setSelected" | "setActiveLabel" | "labelDrag" | "toFlow" | "moveLabel" | "activeLabel" | "removeLabel" | "boxes" | "settledNotes"> }) {
  const { notes, strokes, notePos, screen, viewport, setNotes, editing, markupStore, setEditing, growHost, lineFrom, calledOut, setSelected, setActiveLabel, labelDrag, toFlow, moveLabel, activeLabel, removeLabel, boxes, settledNotes } = model;
  return (<>
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
              markupStore.getState().commitNote(n.id);
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
            markupStore.getState().commitNote(n.id);
          }}
          onCommit={() => setEditing(null)}
          onGrab={(e) => {
            let id = n.id;
            if (e.altKey) {
              const state = markupStore.getState();
              const fragment = captureMarkup({ ...state, notes: settledNotes }, { strokes: [], notes: [n.id] });
              const copy = appendMarkup(state, fragment, { x: 0, y: 0 }, boxes);
              markupStore.setState(copy);
              id = copy.selected.notes[fragment.notes.findIndex((note) => note.id === n.id)]!;
            }
            setSelected(NOTHING_SELECTED);
            setActiveLabel(id);
            labelDrag.current = { id, start: toFlow(e), from: notePos(n) };
            e.currentTarget.setPointerCapture(e.pointerId);
          }}
          onDrag={(e) => {
            const d = labelDrag.current;
            if (!d) return;
            const p = toFlow(e);
            moveLabel(d.id, {
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
  </>);
}

export function ArchivedNotes({ model }: { model: Pick<MarkupModel, "shelf" | "screen" | "viewport" | "filed"> }) {
  const { shelf, screen, viewport, filed } = model;
  return (<>
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
  </>);
}
