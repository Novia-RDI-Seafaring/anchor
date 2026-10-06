import {
  nearestOnStroke,
  rectFrom,
  strokeBounds
} from "./lasso";
import { type Selection } from "./markupStore";
import { CORNERS, ERASE_PX, HANDLE_PX, INK } from "./constants";
import { SketchCross, SketchSquare } from "./InkIcons";
import type { MarkupModel } from "./types";

export function SelectionControls({ model }: { model: Pick<MarkupModel, "marquee" | "screen" | "viewport" | "lone" | "strokes" | "marks" | "removeSelected" | "startGroupDrag" | "onGroupDragMove" | "endGroupDrag" | "picked" | "selected" | "hoveredStroke" | "removeStroke"> }) {
  const { marquee, screen, viewport, lone, strokes, marks, removeSelected, startGroupDrag, onGroupDragMove, endGroupDrag, picked, selected, hoveredStroke, removeStroke } = model;
  return (<>
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
                after a click: the shape is already showing its x here, and
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
  </>);
}
