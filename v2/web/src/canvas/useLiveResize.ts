import { useEffect, useRef, useState } from "react";
import type { OnResize, OnResizeEnd, OnResizeStart } from "@xyflow/react";

/**
 * useLiveResize — give a shape renderer live width/height during an active
 * NodeResizer drag.
 *
 * Why this exists: ReactFlow's `NodeResizer` updates the node wrapper's
 * dimensions live during a drag, but our shape renderers paint their
 * silhouette on an INNER element sized from `data.width` / `data.height`.
 * The store only updates `data.*` on resize-END (see `onNodesChange` in
 * `CanvasGraph.tsx`), so the inner element stayed at the original size for
 * the entire drag and "snapped" only on release.
 *
 * This hook keeps a local mirror of the resize-in-progress dimensions. The
 * shape's inner element renders from `{ width, height }` returned here
 * instead of directly from `data.*`. On `onResizeStart` we mark the drag
 * in flight; on each `onResize` we update local state; on `onResizeEnd` we
 * clear the in-flight flag so subsequent canonical (`data.*`) updates take
 * over again.
 *
 * Wire-up per shape:
 *
 *   const { width, height, handlers } = useLiveResize(d.width, d.height);
 *   ...
 *   <NodeResizer {...handlers} ... />
 *   <div style={{ width, height }}>...</div>
 *
 * The hook returns `undefined` for either dimension when neither `data.*`
 * nor an in-flight drag has set one yet — so shapes can still fall back to
 * their intrinsic / Tailwind-class default size for legacy nodes that
 * predate dimension persistence.
 */
export function useLiveResize(
  dataWidth: number | undefined,
  dataHeight: number | undefined,
): {
  width: number | undefined;
  height: number | undefined;
  handlers: { onResizeStart: OnResizeStart; onResize: OnResize; onResizeEnd: OnResizeEnd };
} {
  const [live, setLive] = useState<{ w?: number; h?: number }>({
    w: dataWidth,
    h: dataHeight,
  });
  const resizingRef = useRef(false);

  // Adopt canonical changes only when no drag is in flight; otherwise the
  // live mirror is authoritative for the duration of the drag.
  useEffect(() => {
    if (resizingRef.current) return;
    setLive({ w: dataWidth, h: dataHeight });
  }, [dataWidth, dataHeight]);

  const onResizeStart: OnResizeStart = () => {
    resizingRef.current = true;
  };
  const onResize: OnResize = (_event, params) => {
    setLive({ w: params.width, h: params.height });
  };
  const onResizeEnd: OnResizeEnd = () => {
    resizingRef.current = false;
  };

  return {
    width: live.w,
    height: live.h,
    handlers: { onResizeStart, onResize, onResizeEnd },
  };
}
