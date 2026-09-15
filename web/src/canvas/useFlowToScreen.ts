/**
 * useFlowToScreen — flow → screen projection for fixed-position overlays.
 *
 * The thread overlays (ask composer, pins, ghost preview) live in screen
 * space like the NodeContextToolbar, so they neither scale with zoom nor
 * fight the ReactFlow viewport transform. Subscribing to the transform and
 * the pane size re-anchors them on every pan / zoom / resize; `paneRect`
 * lets a caller hide markers that fall outside the visible pane.
 */
import { useReactFlow, useStore } from "@xyflow/react";
import { useMemo } from "react";

export type FlowToScreen = {
  toScreen: (p: { x: number; y: number }) => { x: number; y: number };
  zoom: number;
  /** The pane's viewport rect, or null before ReactFlow mounts (tests). */
  paneRect: DOMRect | null;
};

export function useFlowToScreen(): FlowToScreen {
  const transform = useStore((s) => s.transform);
  const width = useStore((s) => s.width);
  const height = useStore((s) => s.height);
  const domNode = useStore((s) => s.domNode);
  const { flowToScreenPosition } = useReactFlow();

  return useMemo(
    () => ({
      toScreen: flowToScreenPosition,
      zoom: transform[2],
      paneRect: domNode?.getBoundingClientRect() ?? null,
    }),
    // flowToScreenPosition is stable for the provider's lifetime; the deps
    // on transform / size are what re-project on pan, zoom and resize.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [transform, width, height, domNode],
  );
}

/** True when a screen point lies inside the pane (or the pane is unknown). */
export function insidePane(rect: DOMRect | null, p: { x: number; y: number }): boolean {
  if (!rect) return true;
  return p.x >= rect.left && p.x <= rect.right && p.y >= rect.top && p.y <= rect.bottom;
}
