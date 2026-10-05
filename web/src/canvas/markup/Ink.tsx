import {
  isLoop,
  lassoHits,
  leaderPath,
  smoothClosedPath
} from "@/canvas/lasso";
import { previewCentre } from "@/canvas/preview";
import { GHOST_GROUNDS } from "@/stores/markupStore";
import { GHOST_H, GHOST_W, INK } from "./constants";
import type { MarkupModel } from "./types";

export function Ink({ model }: { model: Pick<MarkupModel, "remarkBlob" | "screen" | "ground" | "ghosts" | "openFiled" | "viewport" | "storeNodes" | "shelf" | "blobOf" | "hoverShelf" | "notes" | "lineFrom" | "notePos" | "calledOut" | "dropOn" | "boxes" | "ink" | "ids" | "marks" | "paths" | "selected" | "all" | "hoveredStroke" | "surfaceRef" | "lifted" | "onPointerDown" | "onPointerMove" | "onPointerUp" | "onClick" | "onDoubleClick"> }) {
  const { remarkBlob, screen, ground, ghosts, openFiled, viewport, storeNodes, shelf, blobOf, hoverShelf, notes, lineFrom, notePos, calledOut, dropOn, boxes, ink, ids, marks, paths, selected, all, hoveredStroke, surfaceRef, lifted, onPointerDown, onPointerMove, onPointerUp, onClick, onDoubleClick } = model;
  return (<>
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
      className={`absolute inset-0 z-20 ${lifted ? "pointer-events-none" : hoveredStroke !== null ? "cursor-grab" : "cursor-crosshair"
        }`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onClick={onClick as unknown as React.MouseEventHandler}
      onDoubleClick={onDoubleClick as unknown as React.MouseEventHandler}
    />
  </>);
}
