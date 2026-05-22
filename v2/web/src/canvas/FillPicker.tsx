/**
 * FillPicker — single-level swatch panel that patches `data.bg_color`.
 *
 * Surfaced from the Fill chip on the NodeContextToolbar and from the Fill
 * submenu on the right-click NodeContextMenu. ~30 LOC by design; shared
 * grid logic lives in `Swatches.tsx`.
 */
import { BG_SWATCHES } from "./colors";
import { Swatches } from "./Swatches";

type Props = {
  workspaceSlug: string;
  nodeIds: string[];
  getNodeData: (id: string) => Record<string, unknown> | undefined;
  onClose?: () => void;
};

export function FillPicker({ workspaceSlug, nodeIds, getNodeData, onClose }: Props) {
  return (
    <div data-testid="fill-picker" className="min-w-[12rem]">
      <Swatches
        workspaceSlug={workspaceSlug}
        nodeIds={nodeIds}
        getNodeData={getNodeData}
        field="bg_color"
        swatches={BG_SWATCHES}
        pickFrom="bg"
        visual="fill"
        ariaPrefix="fill"
        onClose={onClose}
      />
    </div>
  );
}
