import { useMemo } from "react";
import { intents, INTENTS_CHANGED_EVENT, type Intent } from "@/api/intents";
import { previewCentre, previewOps } from "@/canvas/preview";
import { changesOf, markChanges, removedEdgeEnds } from "@/canvas/changeMarks";
import { stillOnBoard, type OverlayHost, type Intent as OverlayIntent } from "../../intent-overlay";
import type { Box } from "@/canvas/lasso";
import { IntentsSse } from "@/realtime/intentsSse";
import { useAnchorGeometry } from "./AnchorGeometry";

/** Preserve Anchor's public wire shape at the adapter boundary. */
export function toOverlayIntent(intent: Intent): OverlayIntent {
  return { ...intent, targetIds: (intent.targets ?? []).map((target) => target.node_id) };
}
/** How to get an agent reading this project's remarks. */
const LISTEN_HINT = {
  prompt: "Check the Anchor intent inbox (list_pending_intents) and handle what is there.",
  command: "anchor intents",
};
const input: OverlayHost["input"] = {
  capturesLiftedPress: (target) => {
    const el = target as HTMLElement | null;
    return Boolean(el?.closest?.(".react-flow") &&
      !el.closest('[data-testid="ref-review-chip"], [data-source-anchor]'));
  },
  onLiftedChange: (lifted) => {
    if (lifted) document.body.dataset.penLifted = "";
    else delete document.body.dataset.penLifted;
  },
  onPanningChange: (panning) => {
    if (panning) document.body.dataset.penPanning = "";
    else delete document.body.dataset.penPanning;
  },
};
export function useAnchorOverlayHost(workspaceSlug: string, boxes: Box[]): OverlayHost {
  const geometry = useAnchorGeometry();
  const thread = useMemo<OverlayHost["thread"]>(() => ({
    // Open remarks, and resolved ones holding a change the reader has not
    // yet kept or put back.
    loadScoped: async () => (await intents.listAll())
      .filter((intent) => intent.origin_canvas_id === workspaceSlug).map(toOverlayIntent)
      .filter((intent) => intent.status !== "resolved" || stillOnBoard(intent, new Set())),
    get: async (id) => {
      const intent = await intents.get(id);
      return intent ? toOverlayIntent(intent) : null;
    },
    submit: async ({ targetIds, ...remark }) => toOverlayIntent(await intents.create({
      ...remark, workspaceSlug, targets: targetIds,
    })),
    addItem: intents.addItem,
    answer: intents.answer,
    apply: intents.apply,
    revert: intents.revert,
    decline: intents.decline,
    resolve: intents.resolve,
    subscribeChanged: (onChanged) => {
      const sse = new IntentsSse({ onPending: onChanged });
      window.addEventListener(INTENTS_CHANGED_EVENT, onChanged);
      sse.connect();
      return () => {
        sse.disconnect();
        window.removeEventListener(INTENTS_CHANGED_EVENT, onChanged);
      };
    },
  }), [workspaceSlug]);
  return {
    geometry: {
      boxes, viewport: geometry.viewport,
      getViewport: geometry.getViewport, setViewport: geometry.setViewport,
      fitBounds: (rect, options) => geometry.fitBounds(rect, options),
      paneSize: geometry.paneSize,
      screenToWorld: (point) => geometry.toFlow({ clientX: point.x, clientY: point.y }),
      rowsOf: geometry.rowsOf, edgesOf: geometry.edgesOf,
    },
    display: {
      labelOf: (id) => String(geometry.storeNodes[id]?.data?.label ?? id),
      listenHint: LISTEN_HINT,
      preview: (item) => {
        if (!item.ops) return null;
        const preview = previewOps(item.ops, geometry.storeNodes, Object.values(geometry.storeEdges));
        return {
          nodes: preview.nodes,
          stale: preview.stale,
          edges: preview.edges.map((edge) => ({
            id: edge.id, kind: edge.kind,
            from: previewCentre(edge.source, preview, geometry.storeNodes),
            to: previewCentre(edge.target, preview, geometry.storeNodes),
          })),
        };
      },
      changes: (item) => {
        if (!item.undo_ops) return null;
        const { marks, removed } = changesOf(item.undo_ops, geometry.storeNodes, geometry.storeEdges);
        return { marks, removed: { nodes: removed.nodes, edges: removedEdgeEnds(removed, geometry.storeNodes) } };
      },
      markChanges,
    },
    thread, input,
  };
}
