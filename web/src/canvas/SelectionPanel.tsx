import { useParams } from "react-router-dom";

import { FillPicker } from "@/canvas/FillPicker";
import { StrokePicker } from "@/canvas/StrokePicker";
import { TextPicker } from "@/canvas/TextPicker";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

/**
 * SelectionPanel — the properties of whatever is selected, always visible
 * while something is.
 *
 * Excalidraw puts these on the left, open, next to the drawing: pick a
 * shape and its colours, text size and alignment are right there, one click
 * each. Anchor had the same controls hidden behind chips on a floating
 * toolbar, so changing a text size took a click to open a popover and
 * another to choose.
 *
 * Which sections show depends on what is selected. A text element has no
 * fill and no border, so it gets the text controls alone. Everything else
 * gets fill, stroke and text. The panel is empty markup when the selection
 * is empty, so the canvas is unobstructed while nothing is picked.
 */
export function SelectionPanel() {
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const selectedNodeId = useUiStore((s) => s.selectedNodeId);
  const nodes = useCanvasStore((s) => s.nodes);

  if (!workspaceSlug || !selectedNodeId) return null;
  const node = nodes[selectedNodeId];
  if (!node) return null;

  const nodeIds = [selectedNodeId];
  const getNodeData = (nid: string) => nodes[nid]?.data;
  // Text elements are words with no box, so fill and stroke would style
  // nothing the user can see.
  const isText = node.node_type === "text";

  return (
    <div
      data-testid="selection-panel"
      className="pointer-events-auto absolute left-3 top-16 z-20 flex max-h-[calc(100vh-6rem)] w-[17rem] flex-col gap-3 overflow-y-auto rounded-xl border border-neutral-200 bg-white/95 px-3 py-3 shadow-md backdrop-blur"
      aria-label="Selection properties"
    >
      {isText ? null : (
        <>
          <PanelSection label="Fill">
            <FillPicker
              workspaceSlug={workspaceSlug}
              nodeIds={nodeIds}
              getNodeData={getNodeData}
            />
          </PanelSection>
          <PanelSection label="Stroke">
            <StrokePicker
              workspaceSlug={workspaceSlug}
              nodeIds={nodeIds}
              getNodeData={getNodeData}
            />
          </PanelSection>
        </>
      )}
      <PanelSection label="Text">
        <TextPicker
          workspaceSlug={workspaceSlug}
          nodeIds={nodeIds}
          getNodeData={getNodeData}
        />
      </PanelSection>
    </div>
  );
}

function PanelSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
        {label}
      </div>
      {children}
    </section>
  );
}
