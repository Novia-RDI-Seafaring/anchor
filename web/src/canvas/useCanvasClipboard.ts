import { useEffect, useRef, useState } from "react";
import type { Node, Edge } from "@xyflow/react";
import { canvases } from "@/api/canvases";
import { useCanvasStore } from "@/stores/canvasStore";
import { clipboardKey } from "@/shared/clipboard";
import { captureCanvas, planCanvasPaste, type CanvasFragment } from "./clipboard";

// One browser server serves one project. This clipboard lasts for this page session.
let clipboard: { fragment: CanvasFragment; pastes: number } | null = null;
type Point = { x: number; y: number };
type Args = { slug: string; active: boolean; nodes: () => Node[]; edges: () => Edge[];
  toFlow: (point: { x: number; y: number }) => Point; restore: () => void; select: (ids: string[]) => void };

export function useCanvasClipboard(args: Args) {
  const latest = useRef(args); latest.current = args;
  const busy = useRef(false);
  const drag = useRef<{ fragment: CanvasFragment; start: Point; completed: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sync = async (slug: string) => {
    const snapshot = await canvases.state(slug);
    if (latest.current.slug === slug) useCanvasStore.getState().setSnapshot(snapshot);
  };

  const paste = async (fragment: CanvasFragment, offset: Point) => {
    if (busy.current) return;
    busy.current = true; setError(null);
    const { slug } = latest.current;
    const attemptedNodes: string[] = [], attemptedEdges: string[] = [];
    try {
      const plan = planCanvasPaste(fragment, slug, new Set(Object.keys(useCanvasStore.getState().nodes)), offset);
      for (const node of plan.nodes) {
        attemptedNodes.push(node.id);
        await canvases.addNode(slug, node);
      }
      for (const edge of plan.edges) {
        attemptedEdges.push(edge.id);
        await canvases.addEdge(slug, edge);
      }
      if (latest.current.slug === slug) {
        await sync(slug);
        if (latest.current.slug === slug) latest.current.select(plan.nodes.map((n) => n.id));
      }
    } catch (cause) {
      for (const id of attemptedEdges.reverse()) await canvases.removeEdge(slug, id).catch(() => {});
      for (const id of attemptedNodes.reverse()) await canvases.removeNode(slug, id).catch(() => {});
      setError(`Paste failed: ${cause instanceof Error ? cause.message : String(cause)}`);
      if (latest.current.slug === slug) await sync(slug).catch(() => {});
    } finally { busy.current = false; }
  };

  useEffect(() => {
    if (!args.active) return;
    const onKey = (event: KeyboardEvent) => {
      const key = clipboardKey(event);
      if (!key || busy.current) return;
      const current = latest.current;
      if (key === "v") {
        if (!clipboard) return;
        event.preventDefault();
        const step = ++clipboard.pastes * 24;
        void paste(clipboard.fragment, { x: step, y: step });
        return;
      }
      const fragment = captureCanvas(useCanvasStore.getState(), current.slug,
        current.nodes().filter((n) => n.selected).map((n) => n.id), current.edges().filter((e) => e.selected).map((e) => e.id));
      if (!fragment.nodes.length && !fragment.edges.length) return;
      event.preventDefault(); clipboard = { fragment, pastes: 0 }; setError(null);
      if (key === "x") {
        busy.current = true;
        void (async () => {
          try {
            for (const edge of fragment.edges) await canvases.removeEdge(current.slug, edge.id);
            for (const node of [...fragment.nodes].reverse()) await canvases.removeNode(current.slug, node.id);
          } catch (cause) {
            setError(`Cut could not finish. The selection is still on the canvas clipboard: ${String(cause)}`);
          } finally {
            if (latest.current.slug === current.slug) await sync(current.slug).catch(() => {});
            busy.current = false;
          }
        })();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [args.active]);

  const startDrag = (event: { altKey: boolean; clientX: number; clientY: number }, ids: string[]) => {
    drag.current = event.altKey && !busy.current ? {
      fragment: captureCanvas(useCanvasStore.getState(), args.slug, ids),
      start: args.toFlow({ x: event.clientX, y: event.clientY }), completed: false,
    } : null;
  };
  const finishDrag = (event: { clientX: number; clientY: number }) => {
    const pending = drag.current;
    if (!pending) return false;
    if (!pending.completed) {
      pending.completed = true;
      const end = args.toFlow({ x: event.clientX, y: event.clientY });
      args.restore();
      void paste(pending.fragment, { x: end.x - pending.start.x, y: end.y - pending.start.y });
    }
    return true;
  };
  return { startDrag, finishDrag, error };
}
