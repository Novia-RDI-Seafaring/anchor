import { useMemo } from "react";
import { intents, INTENTS_CHANGED_EVENT, type Intent } from "@/api/intents";
import { previewCentre, previewOps } from "@/canvas/preview";
import type { OverlayHost, Intent as OverlayIntent } from "../../intent-overlay";
import type { Box } from "@/canvas/lasso";
import { useAnchorGeometry } from "./AnchorGeometry";

/** Preserve Anchor's public wire shape at the adapter boundary. */
export function toOverlayIntent(intent: Intent): OverlayIntent {
  return { ...intent, targetIds: (intent.targets ?? []).map((target) => target.node_id) };
}
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
    loadScoped: async () => (await intents.listPending())
      .filter((intent) => intent.origin_canvas_id === workspaceSlug).map(toOverlayIntent),
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
      window.addEventListener(INTENTS_CHANGED_EVENT, onChanged);
      return () => window.removeEventListener(INTENTS_CHANGED_EVENT, onChanged);
    },
  }), [workspaceSlug]);
  return {
    geometry: {
      boxes, viewport: geometry.viewport,
      getViewport: geometry.getViewport, setViewport: geometry.setViewport,
      screenToWorld: (point) => geometry.toFlow({ clientX: point.x, clientY: point.y }),
      rowsOf: geometry.rowsOf, edgesOf: geometry.edgesOf,
    },
    display: {
      labelOf: (id) => String(geometry.storeNodes[id]?.data?.label ?? id),
      preview: (item) => {
        if (!item.ops) return null;
        const preview = previewOps(item.ops, geometry.storeNodes, Object.values(geometry.storeEdges));
        return {
          nodes: preview.nodes,
          edges: preview.edges.map((edge) => ({
            id: edge.id, kind: edge.kind,
            from: previewCentre(edge.source, preview, geometry.storeNodes),
            to: previewCentre(edge.target, preview, geometry.storeNodes),
          })),
        };
      },
    },
    thread, input,
  };
}
