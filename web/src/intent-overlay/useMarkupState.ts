import {
  type Point,
  type Rect
} from "./lasso";
import { createMarkupStore } from "./markupStore";
import { useCallback, useEffect, useRef, useState } from "react";
import { useStore } from "zustand";
import type { MarkupModel } from "./types";

export function useMarkupState(context: Pick<MarkupModel, "active" | "host">) {
  const { active, host } = context;
  const [markupStore] = useState(createMarkupStore);

  const {
    marks, ink, notes, ids, manual, hoveredStroke, editing, selected, dropOn,
    activeLabel, sending, filed, openFiled, kept, lifted, hoverShelf, shelf,
    ground, panelAt, answering,
  } = useStore(markupStore);

  const {
    updateNotes: setNotes, setTargets: setIds, setManualTargets: setManual,
    hoverMark: setHoveredStroke, editNote: setEditing, selectMarks: setSelected,
    previewJoin: setDropOn, selectLabel: setActiveLabel, openThread: setOpenFiled,
    liftPen: setLifted, hoverStack: setHoverShelf, movePanel: setPanelAt,
    writeAnswer: setAnswering, keepSuggestion, setMargin: setMarginDeg,
  } = markupStore.getState();

  const [current, renderCurrent] = useState<Point[] | null>(null);

  const currentGesture = useRef<Point[] | null>(null);

  const setCurrent = useCallback((update: React.SetStateAction<Point[] | null>) => {
    const next = typeof update === "function" ? update(currentGesture.current) : update;
    currentGesture.current = next;
    renderCurrent(next);
  }, []);

  const [marquee, renderMarquee] = useState<{ a: Point; b: Point } | null>(null);

  const marqueeGesture = useRef<{ a: Point; b: Point } | null>(null);

  const setMarquee = useCallback((update: React.SetStateAction<typeof marquee>) => {
    const next = typeof update === "function" ? update(marqueeGesture.current) : update;
    marqueeGesture.current = next;
    renderMarquee(next);
  }, []);

  // The hand shows while the pen is up, since a drag now moves the board.
  useEffect(() => {
    if (!lifted) return undefined;
    host.input?.onLiftedChange?.(true);
    return () => {
      host.input?.onLiftedChange?.(false);
    };
  }, [lifted, host.input]);

  const tapRef = useRef<Point | null>(null);

  const panelRef = useRef<HTMLDivElement | null>(null);

  const panelDrag = useRef<{ startX: number; startY: number; x: number; y: number } | null>(null);

  const settle = (intentId: string, judged: Set<string>) => markupStore.getState().settle(intentId, judged, host.thread);

  const drawing = useRef(false);

  /** A stroke just landed: the click that ends it is not a click on it. */
  const drewJustNow = useRef(false);

  const surfaceRef = useRef<HTMLDivElement | null>(null);

  const marqueeDrag = useRef(false);

  const labelDrag = useRef<{ id: string; start: Point; from: Point } | null>(null);

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

  // Geometry, derived. Everything that reads strokes keeps reading points, and
  // the colours ride alongside on the same indices -- so there is no second
  // array to keep in step, which is where colour would otherwise drift.
  const strokes = marks.map((m) => m.points);

  /** Store actions are synchronous, so handlers can read the resulting geometry. */
  const applyMarks = markupStore.getState().replaceMarks;

  const reset = () => {
    markupStore.getState().resetRemark();
    setCurrent(null);
    setMarquee(null);
  };

  useEffect(() => {
    if (!active) {
      markupStore.getState().pauseMarkup();
      // Putting the pen down keeps the ink. Only what was mid-gesture goes:
      // a half-drawn stroke, a selection, a label being carried. What was
      // drawn is still there when the pen comes back,
      // the same as the agent's work on what was already filed. Clearing it
      // on the way out made escape, and the button, a way to lose a remark.
      setCurrent(null);
      setMarquee(null);
    }
  }, [active, markupStore, setCurrent, setMarquee]);

  return { markupStore, marks, ink, notes, ids, manual, hoveredStroke, editing, selected, dropOn, activeLabel, sending, filed, openFiled, kept, lifted, hoverShelf, shelf, ground, panelAt, answering, setNotes, setIds, setManual, setHoveredStroke, setEditing, setSelected, setDropOn, setActiveLabel, setOpenFiled, setLifted, setHoverShelf, setPanelAt, setAnswering, keepSuggestion, setMarginDeg, current, setCurrent, marquee, setMarquee, tapRef, panelRef, panelDrag, settle, drawing, drewJustNow, surfaceRef, marqueeDrag, labelDrag, pullDrag, groupDrag, panning, strokes, applyMarks, reset };
}
