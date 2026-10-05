import { intents } from "@/api/intents";
import { describeCuts } from "@/canvas/cuts";
import {
  exitLoop,
  loopCentre
} from "@/canvas/lasso";
import { describeSketch } from "@/canvas/sketch";
import { GHOST_H, GHOST_W } from "./constants";
import { ReplyLine } from "./ReplyLine";
import { splitGhostText } from "./replyModel";
import type { MarkupModel } from "./types";

export function Replies({ model }: { model: Pick<MarkupModel, "ghosts" | "screen" | "viewport" | "answering" | "setAnswering" | "keepSuggestion" | "settle" | "kept" | "written" | "reading" | "cutsReading" | "reset"> }) {
  const { ghosts, screen, viewport, answering, setAnswering, keepSuggestion, settle, kept, written, reading, cutsReading, reset } = model;
  return (<>
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
            <div className="text-[11px] text-neutral-400">sent {"\u00b7"} waiting for the agent</div>
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
                    const next = keepSuggestion(applied.id);
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
  </>);
}
