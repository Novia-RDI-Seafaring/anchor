import { useEffect, useRef, useState, type RefObject } from "react";

import { canvases } from "@/api/canvases";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";
import { editorAction, planNudge, supportsInlineRename } from "./editorShortcuts";

type Args = {
  rootRef: RefObject<HTMLElement | null>;
  slug: string;
  active: boolean;
  selectedIds: () => string[];
  selectedEdgeIds?: () => string[];
  duplicate: () => void;
};
type Nudge = { slug: string; ids: string[]; dx: number; dy: number };

/** Capture before ReactFlow's local keyboard move so saved state owns the result. */
export function useCanvasKeyboard(args: Args) {
  const latest = useRef(args); latest.current = args;
  const queued = useRef<Nudge[]>([]);
  const running = useRef(false);
  const mounted = useRef(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; queued.current = []; }; }, []);
  useEffect(() => { setError(null); }, [args.slug]);

  useEffect(() => {
    const root = args.rootRef.current;
    if (!root || !args.active) return;
    const sync = async (slug: string) => {
      const snapshot = await canvases.state(slug);
      if (mounted.current && latest.current.slug === slug && useCanvasStore.getState().slug === slug) {
        useCanvasStore.getState().setSnapshot(snapshot);
      }
    };
    const flush = async () => {
      if (running.current) return;
      running.current = true;
      try {
        while (queued.current.length && mounted.current) {
          const job = queued.current.shift()!;
          if (latest.current.slug !== job.slug || !latest.current.active || useCanvasStore.getState().slug !== job.slug) continue;
          const moves = planNudge(useCanvasStore.getState().nodes, job.ids, job.dx, job.dy);
          try {
            for (const move of moves) await canvases.patchNode(job.slug, move.id, { x: move.x, y: move.y });
            // The response need not race its SSE echo. Refresh before the next
            // repeated key so it computes its delta from the saved positions.
            if (moves.length) await sync(job.slug);
          } catch (cause) {
            queued.current = queued.current.filter((pending) => pending.slug !== job.slug);
            if (mounted.current && latest.current.slug === job.slug) setError(`Could not move selection: ${cause instanceof Error ? cause.message : String(cause)}`);
            await sync(job.slug).catch(() => {});
          }
        }
      } finally { running.current = false; }
    };
    const onKey = (event: KeyboardEvent) => {
      const action = editorAction(event);
      if (!action) return;
      const current = latest.current;
      const ids = current.selectedIds();
      if (action.type === "duplicate" ? !ids.length && !current.selectedEdgeIds?.().length : !ids.includes(action.nodeId)) return;
      if (action.type === "rename" && !supportsInlineRename(useCanvasStore.getState().nodes[action.nodeId]?.node_type ?? "")) return;
      event.preventDefault(); event.stopPropagation();
      setError(null);
      if (action.type === "rename") useUiStore.getState().requestInlineRename(action.nodeId);
      else if (action.type === "duplicate") current.duplicate();
      else {
        queued.current.push({ slug: current.slug, ids, dx: action.dx, dy: action.dy });
        void flush();
      }
    };
    root.addEventListener("keydown", onKey, true);
    return () => { queued.current = []; root.removeEventListener("keydown", onKey, true); };
  }, [args.rootRef, args.slug, args.active]);
  return { error };
}
