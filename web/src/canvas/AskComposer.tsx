/**
 * AskComposer — the scoped ask (#344).
 *
 * Opened from the selection toolbar's "Ask agent…" or the context menu for
 * the current selection; anchored under the selection's bounding box in
 * screen space (same positioning idiom as NodeContextToolbar). A textarea
 * plus suggestion chips derived from the selected node types; Enter (or
 * the button) creates the thread via `POST /api/intents` with the
 * selection as `targets[]`, then opens the thread panel on it.
 *
 * Closes on Escape, on an outside pointerdown, and after a successful ask.
 * The composer keeps its own snapshot of the node ids, so a stray click
 * that deselects the nodes does not lose the anchor mid-typing.
 */
import { MessageSquarePlus } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { intents } from "@/api/intents";
import { Button } from "@/components/ui/button";
import { useCanvasStore } from "@/stores/canvasStore";
import { boundingBox, chipsForSelection } from "@/threads/threads";
import { useThreadsStore } from "@/threads/threadsStore";

import { useFlowToScreen } from "./useFlowToScreen";

type Props = { workspaceSlug: string };

const COMPOSER_WIDTH = 320;
const GAP = 12;

export function AskComposer({ workspaceSlug }: Props) {
  const nodeIds = useThreadsStore((s) => s.composerNodeIds);
  const closeComposer = useThreadsStore((s) => s.closeComposer);
  const openThread = useThreadsStore((s) => s.openThread);
  const nodes = useCanvasStore((s) => s.nodes);
  const { toScreen } = useFlowToScreen();

  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const key = nodeIds?.join(",") ?? "";

  // A fresh selection gets a fresh draft and focus.
  useEffect(() => {
    setText("");
    setError(null);
    if (key) textareaRef.current?.focus();
  }, [key]);

  useEffect(() => {
    if (!nodeIds) return;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") closeComposer();
    };
    const onDown = (ev: PointerEvent) => {
      if (!ref.current) return;
      if (!ref.current.contains(ev.target as Node)) closeComposer();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onDown, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onDown, true);
    };
  }, [nodeIds, closeComposer]);

  if (!nodeIds) return null;
  const box = boundingBox(nodeIds, nodes);
  if (!box) return null;

  const nodeTypes = nodeIds.map((id) => nodes[id]?.node_type).filter((t): t is string => Boolean(t));
  const chips = chipsForSelection(nodeTypes);
  const tl = toScreen({ x: box.x, y: box.y });
  const br = toScreen({ x: box.x + box.width, y: box.y + box.height });
  const viewportW = typeof window !== "undefined" ? window.innerWidth : Infinity;
  const left = Math.max(8, Math.min(tl.x, viewportW - COMPOSER_WIDTH - 8));

  const submit = async (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      const intent = await intents.ask({ text: trimmed, workspaceSlug, nodeIds });
      setError(null);
      openThread(intent.id);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      ref={ref}
      data-testid="ask-composer"
      role="dialog"
      aria-label="Ask the agent about this selection"
      style={{
        position: "fixed",
        left,
        top: br.y + GAP,
        width: COMPOSER_WIDTH,
        zIndex: 31,
      }}
      onMouseDown={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
      className="rounded-md border border-neutral-200 bg-white p-2 shadow-lg"
    >
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
          Ask agent · {nodeIds.length} {nodeIds.length === 1 ? "element" : "elements"}
        </span>
        <button
          type="button"
          onClick={closeComposer}
          className="rounded px-1 text-[10px] text-neutral-400 hover:bg-neutral-200 hover:text-neutral-700"
          title="Close"
          aria-label="Close ask composer"
          data-testid="ask-composer-close"
        >
          ✕
        </button>
      </div>
      <textarea
        ref={textareaRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            void submit(text);
          }
        }}
        rows={2}
        placeholder="What should the agent do with these? (Enter to ask)"
        aria-label="Ask text"
        data-testid="ask-composer-input"
        className="w-full resize-none rounded border border-neutral-300 bg-white px-1.5 py-1 text-xs placeholder:italic placeholder:text-neutral-400"
      />
      <div className="mt-1 flex flex-wrap gap-1" data-testid="ask-composer-chips">
        {chips.map((chip) => (
          <button
            key={chip}
            type="button"
            data-testid="ask-composer-chip"
            onClick={() => void submit(chip)}
            disabled={busy}
            className="rounded-full border border-neutral-300 bg-neutral-50 px-2 py-0.5 text-[10px] text-neutral-700 hover:bg-neutral-100 disabled:opacity-40"
          >
            {chip}
          </button>
        ))}
      </div>
      <div className="mt-1.5 flex items-center justify-between gap-2">
        {error ? (
          <span className="min-w-0 truncate text-[10px] text-red-600" data-testid="ask-composer-error">
            error: {error}
          </span>
        ) : (
          <span className="text-[9px] italic text-neutral-400">
            the agent replies in a thread pinned to this selection
          </span>
        )}
        <Button
          variant="outline"
          size="sm"
          onClick={() => void submit(text)}
          disabled={!text.trim() || busy}
          data-testid="ask-composer-submit"
          className="shrink-0"
        >
          <MessageSquarePlus className="size-3.5" />
          <span className="text-[11px]">Ask</span>
        </Button>
      </div>
    </div>
  );
}
