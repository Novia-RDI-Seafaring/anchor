import { useEffect, useRef, useState, type MouseEvent } from "react";

import { canvases } from "@/api/canvases";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

type Args = {
  slug: string;
  active: boolean;
  toFlow: (point: { x: number; y: number }) => { x: number; y: number };
};

function emptyPane(event: MouseEvent): Element | null {
  const target = event.target;
  if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return null;
  return target instanceof Element && target.matches(".react-flow__pane")
    && !target.closest('[role="dialog"], [data-canvas-read-only="true"]') ? target : null;
}

/** Track both clicks so a placing tool cannot become text after it disarms. */
export function usePaneText(args: Args) {
  const latest = useRef(args); latest.current = args;
  const first = useRef<{ slug: string; pane: Element | null } | null>(null);
  const mounted = useRef(true);
  const busy = useRef(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { first.current = null; setError(null); }, [args.slug]);

  const onMouseDownCapture = (event: MouseEvent) => {
    const current = latest.current;
    const pane = current.active ? emptyPane(event) : null;
    if (event.detail === 1) first.current = { slug: current.slug, pane };
    else if (event.detail === 2 && (first.current?.slug !== current.slug || first.current.pane !== pane)) first.current = null;
  };

  const onDoubleClickCapture = (event: MouseEvent) => {
    const current = latest.current;
    const pane = current.active ? emptyPane(event) : null;
    const start = first.current;
    first.current = null;
    if (!pane || start?.slug !== current.slug || start.pane !== pane) return;
    // Consume before ReactFlow's native double-click zoom sees the event.
    event.preventDefault(); event.stopPropagation();
    if (busy.current) return;
    busy.current = true;
    const point = current.toFlow({ x: event.clientX, y: event.clientY });
    const slug = current.slug;
    setError(null);
    void canvases.addNode(slug, { node_type: "text", label: "", x: point.x, y: point.y, data: { text: "" } })
      .then((response) => {
        if (!mounted.current || latest.current.slug !== slug || !latest.current.active || useCanvasStore.getState().slug !== slug) return;
        const id = (response as { event?: { payload?: { id?: string } } } | null)?.event?.payload?.id;
        if (id) {
          useUiStore.getState().setSelectedNodeId(id);
          useUiStore.getState().requestInlineRename(id);
        }
      })
      .catch((cause) => {
        if (mounted.current && latest.current.slug === slug) setError(`Could not create text: ${cause instanceof Error ? cause.message : String(cause)}`);
      })
      .finally(() => { busy.current = false; });
  };

  return { onMouseDownCapture, onDoubleClickCapture, error };
}
