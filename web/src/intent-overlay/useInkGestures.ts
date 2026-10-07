import {
  clearSpot,
  clipToBox,
  dropTarget,
  insidePolygon,
  insideStroke,
  isLoop,
  lassoHits,
  lineOutOfLoop,
  loopAndTail,
  loopCentre,
  markHits,
  MIN_STROKE_PX,
  nearRect,
  pullStroke,
  rectFrom,
  rimReach,
  ringOutline,
  strokeAt,
  strokeBounds,
  strokeHeading,
  strokeLength,
  toggleId
} from "./lasso";
import { NOTHING_SELECTED } from "./markupStore";
import { CALLOUT_GAP_PX, NOTE_H, NOTE_W, SNAP_PX } from "./constants";
import { hitsNote, noteRect, withinBand } from "./geometry";
import type { MarkupModel } from "./types";

export function useInkGestures(context: Pick<MarkupModel, "active" | "getViewport" | "panning" | "editing" | "setEditing" | "marqueeDrag" | "toFlow" | "setSelected" | "setMarquee" | "setNotes" | "setActiveLabel" | "markupStore" | "pullDrag" | "startGroupDrag" | "drawing" | "setHoveredStroke" | "setCurrent" | "groupDrag" | "onGroupDragMove" | "applyMarks" | "setIds" | "manual" | "boxes" | "setViewport" | "shelfAt" | "setHoverShelf" | "setManual" | "setDropOn" | "endGroupDrag" | "drewJustNow" | "tapRef" | "switchTo" | "offScreen" | "setMarginDeg">) {
  const { active, getViewport, panning, editing, setEditing, marqueeDrag, toFlow, setSelected, setMarquee, setNotes, setActiveLabel, markupStore, pullDrag, startGroupDrag, drawing, setHoveredStroke, setCurrent, groupDrag, onGroupDragMove, applyMarks, setIds, manual, boxes, setViewport, shelfAt, setHoverShelf, setManual, setDropOn, endGroupDrag, drewJustNow, tapRef, switchTo, offScreen, setMarginDeg } = context;
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
      const hit = strokeAt(p, markupStore.getState().marks.map((mark) => mark.points), 10 / Math.max(0.1, getViewport().zoom));
      if (hit >= 0 && !new Set(markupStore.getState().notes.map((note) => note.onStroke)).has(hit)) {
        // Option held: pull the line here rather than move the shape. The
        // reach is a quarter of the line, so a ring drawn a row short is
        // pulled over the row without the rest of it going anywhere.
        if (e.altKey) {
          e.preventDefault();
          e.stopPropagation();
          (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
          const points = markupStore.getState().marks.map((mark) => mark.points)[hit]!;
          let length = 0;
          for (let i = 1; i < points.length; i++) {
            length += Math.hypot(points[i]!.x - points[i - 1]!.x, points[i]!.y - points[i - 1]!.y);
          }
          pullDrag.current = { index: hit, grab: p, start: p, points, reach: length / 4 };
          setSelected(NOTHING_SELECTED);
          setActiveLabel(null);
          return;
        }
        const inSelection = markupStore.getState().selected.strokes.includes(hit);
        if (!inSelection) {
          setSelected(NOTHING_SELECTED);
          setActiveLabel(null);
        }
        startGroupDrag("move", undefined, inSelection ? markupStore.getState().selected : { strokes: [hit], notes: [] })(e);
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
      const nextStrokes = markupStore.getState().marks.map((mark) => mark.points).map((st, i) => (i === pull.index ? next : st));
      applyMarks(markupStore.getState().marks.map((m, i) => ({ ...m, points: nextStrokes[i]! })));
      setIds(manual ?? markHits(nextStrokes, boxes));
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
      // Which drawn stroke is under the pointer, so its x can appear.
      const slack = 10 / Math.max(0.1, getViewport().zoom);
      const hit = strokeAt(p, markupStore.getState().marks.map((mark) => mark.points), slack);
      const next = hit >= 0 && !new Set(markupStore.getState().notes.map((note) => note.onStroke)).has(hit) ? hit : null;
      setHoveredStroke((prev) => (prev === next ? prev : next));
      const over = next === null ? shelfAt(p) : null;
      setHoverShelf((prev) => (prev === over ? prev : over));
      return;
    }
    setCurrent((prev) => {
      const nextStroke = prev ? [...prev, p] : [p];
      // Live, so the reader watches a line become a ring.
      setIds(markHits([...markupStore.getState().marks.map((mark) => mark.points), nextStroke], boxes));
      setManual(null);
      const slack = SNAP_PX / Math.max(0.1, getViewport().zoom);
      const onto = isLoop(nextStroke)
        ? null
        : dropTarget(nextStroke, boxes, slack);
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
        if (m) setSelected(withinBand(rectFrom(m.a, m.b), markupStore.getState().marks.map((mark) => mark.points), markupStore.getState().notes));
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
      if (hit) switchTo(hit);
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
      const slack = SNAP_PX / Math.max(0.1, getViewport().zoom);
      const onto = isLoop(cur) ? null : dropTarget(cur, boxes, slack);
      const start = cur[0]!;
      const leftFrom =
        boxes.find(
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
          : markupStore.getState().marks.findIndex((m) => {
            if (!isLoop(m.points)) return false;
            const outline = ringOutline(m.points);
            return outline.length >= 3 && insidePolygon(cur[0]!, outline);
          });
      const pen = shapeIndex >= 0 ? markupStore.getState().marks[shapeIndex]!.color : markupStore.getState().ink;
      applyMarks([
        ...markupStore.getState().marks,
        ...(split && line.length > 1
          ? [
            { points: split.loop, color: markupStore.getState().ink },
            { points: line, color: markupStore.getState().ink },
          ]
          : [
            {
              points,
              color: pen,
              ...(onto ? { link: { from: leftFrom, to: onto.id } } : {}),
            },
          ]),
      ]);
      const next = markupStore.getState().marks.map((mark) => mark.points);
      drewJustNow.current = true;
      setDropOn(null);
      const hits = markHits(next, boxes);
      setIds(hits);
      // What THIS shape caught, which is a different question from what the
      // whole mark is about. Judging by the mark meant a fresh box drawn on
      // empty canvas inherited the hits of an earlier stroke, and was offered
      // a leader out to a card it had nothing to do with.
      const caught = lassoHits(cur, boxes);
      // Every ring that catches something gets its own offer. Gating on "no
      // notes at all" meant the first remark used up the offer for the whole
      // mark: ringing a second thing left the reader with nowhere to type and
      // no sign of why. Only an offer nobody has taken blocks another.
      const pendingOffer = markupStore.getState().notes.some((n) => n.offered && !n.text.trim());
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
            color: markupStore.getState().ink,
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
          : markupStore.getState().marks.map((mark) => mark.points).findIndex((st, i) => {
            if (i >= markupStore.getState().marks.map((mark) => mark.points).length - 1 || !isLoop(st)) return false;
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
          const zoom = Math.max(0.2, getViewport().zoom);
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
              ...boxes,
              // Not the ring itself: its bounding box is what the words are
              // being placed outside of, and counting it blocked every
              // direction but straight up and down for a ring of any size.
              ...markupStore.getState().marks.map((mark) => mark.points).filter((_, i) => i !== next.length - 1).map(strokeBounds),
              ...markupStore.getState().notes.filter((n) => n.inStroke === undefined).map(noteRect),
              ...offScreen(),
            ],
            gap / 2,
            markupStore.getState().marginDeg ?? undefined,
          );
          // Remember which way this one went, so the next lines up with it --
          // when it went sideways. A margin is a side of the page; an offer
          // that had to go up or down was making do, and remembering it sent
          // the next ring's words straight down past two clear sides.
          const went = (Math.atan2(at.y - centre.y, at.x - centre.x) * 180) / Math.PI;
          setMarginDeg(Math.abs(Math.cos((went * Math.PI) / 180)) >= Math.SQRT1_2 ? went : null);
          setNotes((prev) => [
            ...prev,
            {
              id,
              x: at.x,
              y: at.y,
              text: "",
              ringStroke: next.length - 1,
              offered: true,
              color: markupStore.getState().ink,
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
              color: markupStore.getState().ink,
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
    const inside = markupStore.getState().marks.map((mark) => mark.points).findIndex((st) => insideStroke(p, st));
    // Writing in a shape that already holds words picks those words back up.
    // Adding a second note in the same box would stack two lots of text in
    // one place, and the reader meant to edit what is there.
    const existing = markupStore.getState().notes.find((n) =>
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
        color: markupStore.getState().ink,
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
      const hit = strokeAt(p, markupStore.getState().marks.map((mark) => mark.points), 10 / Math.max(0.1, getViewport().zoom));
      const own = hit >= 0 && !new Set(markupStore.getState().notes.map((note) => note.onStroke)).has(hit);
      setSelected(own ? { strokes: [hit], notes: [] } : NOTHING_SELECTED);
      // Clicking a label's line is clicking the label: one object.
      const owner =
        hit >= 0 && !own
          ? (markupStore.getState().notes.find((n) => n.onStroke === hit)?.id ?? null)
          : null;
      setActiveLabel(owner);
      return;
    }
    const p = toFlow(e);
    const hit = [...boxes]
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

  return { onPointerDown, onPointerMove, onPointerUp, onDoubleClick, onClick };
}
