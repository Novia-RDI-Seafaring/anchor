import {
  exitLoop,
  loopCentre
} from "./lasso";
import { GHOST_GROUNDS, PALETTE } from "./markupStore";
import { Plus, WandSparkles } from "lucide-react";
import { PANEL_INSET_PX } from "./constants";
import type { MarkupModel } from "./types";

export function Hotbar({ model }: { model: Pick<MarkupModel, "lifted" | "onExit" | "newStack" | "shelf" | "reveal" | "markupStore" | "switchTo" | "ink" | "ground" | "marks" | "notes" | "ids"> }) {
  const { lifted, onExit, newStack, shelf, reveal, markupStore, switchTo, ink, ground, marks, notes, ids } = model;
  return (<>
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
        title={"mark up (i) \u2014 press to put the pen down"}
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
        title={"new remark (n) \u2014 set this one aside, unsent, and start another"}
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
            const words = st.notes.map((n) => n.text.trim()).filter(Boolean).join(" \u00b7 ");
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
                    reveal({ marks: markupStore.getState().marks, notes: markupStore.getState().notes, ids });
                    return;
                  }
                  const target = markupStore.getState().shelf.find((x) => x.id === st.id);
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
              markupStore.getState().recolour(pen.ink);
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
  </>);
}

export function SendRemark({ model }: { model: Pick<MarkupModel, "sayable" | "remarkBlob" | "screen" | "all" | "sending" | "sendRemark" | "ids" | "reset"> }) {
  const { sayable, remarkBlob, screen, all, sending, sendRemark, ids, reset } = model;
  return (<>
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
            {sending ? "sending\u2026" : "send to agent"}
            {ids.length > 0 ? ` \u00b7 ${ids.length} node${ids.length === 1 ? "" : "s"}` : ""}
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
            {"\u00d7"}
          </button>
        </div>
      );
    })() : null}
  </>);
}

export function Readout({ model }: { model: Pick<MarkupModel, "panelRef" | "panelAt" | "panelDrag" | "setPanelAt" | "lifted" | "dropOn" | "editing" | "current" | "looping" | "strokes" | "cutsReading" | "host" | "strikesReading" | "reading" | "ids" | "written" | "shelf" | "filed" | "ghosts" | "openFiled" | "setOpenFiled"> }) {
  const { panelRef, panelAt, panelDrag, setPanelAt, lifted, dropOn, editing, current, looping, strokes, cutsReading, host, strikesReading, reading, ids, written, shelf, filed, ghosts, openFiled, setOpenFiled } = model;
  return (<>
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
            ? "pen up \u00b7 hover and click what is underneath \u00b7 release space to draw"
            : dropOn
              ? "let go to join these two"
              : editing
                ? "enter when you have finished writing \u00b7 shift+enter for a new row"
                : current
                  ? looping
                    ? "ring \u2014 taking what the area touches"
                    : "line \u2014 taking what it crosses"
                  : strokes.length > 0
                    ? `${strokes.length} stroke${strokes.length > 1 ? "s" : ""} \u00b7 keep drawing, or double-click to write`
                    : "draw across or around things \u00b7 double-click to write"}
        </span>
      </div>
      {cutsReading.length > 0 ? (
        <div className="mt-1 text-[11px] text-violet-700" data-testid="comment-lasso-cuts">
          {cutsReading.map((c) => (
            <div key={`${c.node}-${c.after}`}>
              cuts <b>{host.display.labelOf(c.node)}</b> after row{" "}
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
              <b>{host.display.labelOf(k.source)}</b> {"\u2192"}{" "}
              <b>{host.display.labelOf(k.target)}</b>
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
        cmd-click a node to add or remove it {"\u00b7"} shift-drag to pick out marks {"\u00b7"} n
        sets this remark aside and starts another {"\u00b7"} drag a line to move it,
        option-drag to pull it {"\u00b7"} hold space to lift the pen and look underneath
        {" \u00b7"} esc puts the pen down, the ink stays
        {shelf.length > 0
          ? ` \u00b7 ${shelf.length} set aside: press its tile, or tap its ground, to go on with it`
          : ""}
      </div>


      {/* What has been sent and is still on the board: each one opens to
            its thread -- the ask, then everything the agent said and did,
            then the proposal -- in the order it happened. */}
      {filed.length > 0 ? (
        <div className="mt-2 border-t border-neutral-200 pt-2" data-testid="comment-lasso-filed">
          <div className="text-[11px] font-medium text-neutral-600">
            {filed.length} sent {"\u00b7"} on the board
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
                            {" \u00b7 "}
                            {it.type}
                            {it.state ? ` \u00b7 ${it.state}` : ""}
                            {": "}
                          </span>
                          {it.text}
                          {it.answer ? <span className="text-neutral-500"> {"\u2192"} {it.answer}</span> : null}
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
  </>);
}
