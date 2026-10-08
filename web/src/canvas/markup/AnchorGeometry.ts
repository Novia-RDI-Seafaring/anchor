import { type RowBand } from "@/canvas/cuts";
import {
  type Point
} from "@/canvas/lasso";
import { type EdgePath } from "@/canvas/strikes";
import { useCanvasStore } from "@/stores/canvasStore";
import { useReactFlow, useViewport } from "@xyflow/react";
import { useCallback } from "react";

export function useAnchorGeometry() {
  const { screenToFlowPosition, getViewport, setViewport } = useReactFlow();

  const storeNodes = useCanvasStore((st) => st.nodes);

  const storeEdges = useCanvasStore((st) => st.edges);

  /**
     * Where a card's rows sit, in canvas coordinates.
     *
     * The rendered table is the only thing that knows this -- row heights come
     * from wrapped text and fonts, not from data -- so the rows are read off
     * the DOM in order and zipped with the store's row keys. Null for a card
     * that has no rows to cut between.
     */
  const rowsOf = useCallback(
    (nodeId: string): RowBand[] | null => {
      const rows = (useCanvasStore.getState().nodes[nodeId]?.data as { rows?: { key?: string }[] } | undefined)
        ?.rows;
      if (!rows || rows.length < 2) return null;
      // Node ids are plain slugs, but escape when the platform can: jsdom may not.
      const safe = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(nodeId) : nodeId;
      const el = document.querySelector(`.react-flow__node[data-id="${safe}"]`);
      if (!el) return null;
      const trs = Array.from(el.querySelectorAll("tr[data-row-handle-id]"));
      if (trs.length !== rows.length) return null;
      return trs.map((tr, i) => {
        const r = tr.getBoundingClientRect();
        const top = screenToFlowPosition({ x: r.left, y: r.top });
        const bottom = screenToFlowPosition({ x: r.left, y: r.bottom });
        return { key: String(rows[i]?.key ?? i + 1), top: top.y, bottom: bottom.y };
      });
    },
    [screenToFlowPosition],
  );

  /**
     * Every edge as it is drawn right now, sampled along its path.
     *
     * Read from the DOM for the same reason rows are: the browser is the only
     * place that knows where a routed curve actually runs, and a cross drawn
     * over it has to be matched against that, not against its endpoints.
     */
  const edgesOf = useCallback((): EdgePath[] => {
    const out: EdgePath[] = [];
    for (const [id, edge] of Object.entries(useCanvasStore.getState().edges)) {
      const safe = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(id) : id;
      const el = document.querySelector<SVGPathElement>(
        `.react-flow__edge[data-id="${safe}"] path.react-flow__edge-path`,
      );
      if (!el || typeof el.getTotalLength !== "function") continue;
      const total = el.getTotalLength();
      if (!Number.isFinite(total) || total <= 0) continue;
      const svg = el.ownerSVGElement;
      const ctm = el.getScreenCTM();
      if (!svg || !ctm) continue;
      const points: Point[] = [];
      const step = Math.max(8, total / 64);
      for (let d = 0; d <= total; d += step) {
        const at = el.getPointAtLength(d).matrixTransform(ctm);
        points.push(screenToFlowPosition({ x: at.x, y: at.y }));
      }
      out.push({ id, source: edge.source, target: edge.target, points });
    }
    return out;
  }, [screenToFlowPosition]);

  // Subscribed, not read on demand. Nothing re-rendered this overlay when the
  // canvas panned or zoomed, so the ink kept the screen coordinates it had
  // when it was drawn and slid out of register with the cards underneath.
  const viewport = useViewport();

  const toFlow = useCallback(
    (e: { clientX: number; clientY: number }) =>
      screenToFlowPosition({ x: e.clientX, y: e.clientY }),
    [screenToFlowPosition],
  );

  return { getViewport, setViewport, storeNodes, storeEdges, rowsOf, edgesOf, viewport, toFlow };
}
