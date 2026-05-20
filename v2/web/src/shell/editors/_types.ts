/**
 * Shared editor types.
 *
 * Each editor in this folder accepts the same shape so the dispatcher in
 * PropertiesPanel.dispatch.ts can pick one by `node.node_type` without
 * caring about its concrete prop signature.
 */
export type CanvasNodeShape = {
  id: string;
  node_type: string;
  label: string;
  x: number;
  y: number;
  data?: Record<string, unknown>;
};

export type EditorProps = {
  workspaceSlug: string;
  node: CanvasNodeShape;
};
