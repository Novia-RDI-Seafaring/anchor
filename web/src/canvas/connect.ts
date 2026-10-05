/**
 * The connector tool's decision, as a pure function (#toolbar connector).
 *
 * Connections attach to whole elements, so drawing one is two clicks: the
 * first picks where the connector starts, the second picks what it ends at.
 * Clicking the same element twice cancels. The tool stays armed after a
 * connector lands, so several can be drawn in a row.
 *
 * The rule lives here rather than inside the canvas click handler so it can
 * be tested without mounting ReactFlow.
 */

/** What a click on an element should do while the connector tool is armed. */
export type ConnectAction =
  | { type: "start"; source: string }
  | { type: "cancel" }
  | { type: "create"; source: string; target: string };

/**
 * Decide what a click on `nodeId` means, given the element the user already
 * picked (`sourceId`, null when no connector is half-drawn).
 */
export function connectClick(sourceId: string | null, nodeId: string): ConnectAction {
  if (!sourceId) return { type: "start", source: nodeId };
  if (sourceId === nodeId) return { type: "cancel" };
  return { type: "create", source: sourceId, target: nodeId };
}
