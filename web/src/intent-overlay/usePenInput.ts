import { NOTHING_SELECTED, PALETTE } from "./markupStore";
import { useEffect, useEffectEvent } from "react";
import type { MarkupModel } from "./types";

export function usePenInput(context: Pick<MarkupModel, "active" | "surfaceRef" | "getViewport" | "setViewport" | "setLifted" | "markupStore" | "newStack" | "removeLabel" | "removeSelected" | "setSelected" | "onExit" | "host">) {
  const { active, surfaceRef, getViewport, setViewport, setLifted, markupStore, newStack, removeLabel, removeSelected, setSelected, onExit, host } = context;
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
  }, [active, getViewport, setViewport, surfaceRef]);

  const onKey = useEffectEvent((e: KeyboardEvent) => {
    // Keys typed into a field belong to the field. Escape there leaves the
    // words; here it would clear every mark on the board, and backspace
    // there deletes a letter, not the label being written in.
    const target = e.target as HTMLElement | null;
    if (target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.isContentEditable) return;
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
      markupStore.getState().recolour(pen.ink);
      return;
    }
    // n: a new remark, the current one set aside unsent.
    if (e.key === "n" && !e.metaKey && !e.ctrlKey && !e.altKey) {
      e.preventDefault();
      newStack();
      return;
    }
    // Delete takes what has been picked out. Nothing picked out means
    // nothing to delete -- it never falls through to clearing the mark.
    if (e.key === "Delete" || e.key === "Backspace") {
      if (markupStore.getState().activeLabel) {
        e.preventDefault();
        removeLabel(markupStore.getState().activeLabel!);
        return;
      }
      if (markupStore.getState().selected.strokes.length + markupStore.getState().selected.notes.length === 0) return;
      e.preventDefault();
      removeSelected();
      return;
    }
    if (e.key !== "Escape") return;
    // Escape puts the selection down first. Starting the whole mark over is
    // a bigger thing than letting go of what is picked out, and pressing
    // escape to get out of a selection should not cost the reader the lot.
    if (markupStore.getState().selected.strokes.length + markupStore.getState().selected.notes.length > 0) {
      setSelected(NOTHING_SELECTED);
      return;
    }
    // Nothing picked out: the only thing left to back out of is the mode.
    // Escape never clears the ink. It used to, when there was ink and no
    // selection, and one press too many after leaving a field wiped a
    // whole remark with no way back. The ink is kept and waits for the pen
    // to come back down; deleting is a selection and a delete key.
    onExit?.();
  });

  useEffect(() => {
    if (!active) {
      setLifted(false);
      return undefined;
    }
    // With the pen up, a drag moves the board under it: the hand tool of
    // every drawing program, held on the same key. A trackpad has no middle
    // button, and leaving the mode just to look elsewhere lost the pen.
    let pan: { x: number; y: number; vx: number; vy: number } | null = null;
    const endPan = () => {
      pan = null;
      host.input?.onPanningChange?.(false);
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
      if (!markupStore.getState().lifted) return;
      if (!host.input?.capturesLiftedPress?.(e.target)) return;
      e.stopPropagation();
      e.preventDefault();
      if (e.type === "pointerdown" && (e as PointerEvent).button === 0) {
        const pe = e as PointerEvent;
        const vp = getViewport();
        pan = { x: pe.clientX, y: pe.clientY, vx: vp.x, vy: vp.y };
        host.input?.onPanningChange?.(true);
      }
    };
    // The pen goes down again if the window loses focus mid-hold, so a
    // cmd-tab away never leaves the surface transparent.
    const onBlur = () => {
      endPan();
      setLifted(false);
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
    // onKey is an effect event, intentionally excluded from dependencies.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, getViewport, setViewport, markupStore, setLifted, host.input]);

}
