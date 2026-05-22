/**
 * StrokePicker — single-level swatch panel that patches `data.stroke_color`.
 *
 * Surfaced from the Stroke chip on the NodeContextToolbar and from the
 * Stroke submenu on the right-click NodeContextMenu. ~30 LOC by design.
 */
import { STROKE_SWATCHES } from "./colors";
import { Swatches } from "./Swatches";

type Props = {
  workspaceSlug: string;
  nodeIds: string[];
  getNodeData: (id: string) => Record<string, unknown> | undefined;
  onClose?: () => void;
};

export function StrokePicker({ workspaceSlug, nodeIds, getNodeData, onClose }: Props) {
  return (
    <div data-testid="stroke-picker" className="min-w-[12rem]">
      <Swatches
        workspaceSlug={workspaceSlug}
        nodeIds={nodeIds}
        getNodeData={getNodeData}
        field="stroke_color"
        swatches={STROKE_SWATCHES}
        pickFrom="stroke"
        visual="stroke"
        ariaPrefix="stroke"
        onClose={onClose}
      />
    </div>
  );
}
