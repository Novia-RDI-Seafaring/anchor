import { useParams } from "react-router-dom";

import { FillPicker } from "@/canvas/FillPicker";
import { StrokePicker } from "@/canvas/StrokePicker";
import { TextPicker } from "@/canvas/TextPicker";
import { NodePresentationEditor } from "@/canvas/NodePresentationEditor";
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
export function SelectionPanel({ nodeIds: selection, onAsk }: {
  nodeIds?: string[];
  onAsk?: () => void;
} = {}) {
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const selectedNodeId = useUiStore((s) => s.selectedNodeId);
  const nodes = useCanvasStore((s) => s.nodes);

  const nodeIds = selection ?? (selectedNodeId ? [selectedNodeId] : []);
  if (!workspaceSlug || nodeIds.length !== 1) return null;
  const node = nodes[nodeIds[0]!];
  if (!node) return null;

  const getNodeData = (nid: string) => nodes[nid]?.data;
  // Text elements are words with no box, so fill and stroke would style
  // nothing the user can see.
  const isText = node.node_type === "text" || node.data?.role === "heading";

  return (
    <div
      data-testid="selection-panel"
      // Leave room for the tool rail, including its scrollbar on short canvases.
      // Bound the panel to the canvas and let its controls shrink or wrap.
      // Its controls also stay above the selected node's quick-connect dots.
      className="pointer-events-auto absolute left-20 top-16 z-30 flex max-h-[calc(100%_-_5rem)] w-[17rem] max-w-[calc(100%_-_6rem)] flex-col gap-3 overflow-y-auto rounded-xl border border-neutral-200 bg-white/95 px-3 py-3 shadow-md backdrop-blur [&>section>div]:min-w-0 [&>section>label]:flex-wrap"
      aria-label="Selection properties"
    >
      {onAsk ? <button type="button" onClick={onAsk} className="rounded border border-neutral-300 bg-white px-2 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50">Ask agent</button> : null}
      <NodePresentationEditor workspaceSlug={workspaceSlug} node={node} />
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
