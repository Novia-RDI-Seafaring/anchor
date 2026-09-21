import { Anchor as AnchorIcon } from "lucide-react";

import type { ResolvableRef } from "@/api/documents";
import { useOpenSourceRef } from "@/canvas/useOpenSourceRef";
import { useRefHover } from "@/canvas/useRefHover";
import { useUiStore } from "@/stores/uiStore";

/**
 * SourceAnchorButton — the anchor glyph that opens a ref, on a card.
 *
 * `SourceRefLink` is the same idea for a ref written inline in prose: the
 * words, then the anchor. This is the bare glyph, for places where the ref
 * belongs to a row or a card rather than to a sentence -- a spec row's source,
 * a card-level fallback.
 *
 * Both share `useRefHover`, so hovering either one does the same thing. They
 * used not to: the anchors in a spec table were plain buttons that answered
 * only to a click, so the same glyph was live in one place and dead in
 * another, which reads as the preview being broken rather than absent.
 */
export function SourceAnchorButton({
  workspaceSlug,
  documentNodeId,
  refValue,
  query,
  title,
  ariaLabel,
  size = 11,
  className = "",
}: {
  workspaceSlug: string | undefined;
  /** The document card this ref belongs to, when the caller knows it. */
  documentNodeId?: string;
  refValue: ResolvableRef;
  /** Text to highlight inside the region, when the caller has it. */
  query?: string;
  title?: string;
  ariaLabel?: string;
  size?: number;
  className?: string;
}) {
  const openRef = useOpenSourceRef(workspaceSlug, { documentNodeId });
  const pinViewer = useUiStore((s) => s.pinPdfViewer);
  const { hoverProps, preview, cancelTimers } = useRefHover(workspaceSlug, refValue, query);

  return (
    <button
      type="button"
      className={`nodrag nopan inline-grid place-items-center rounded text-sky-700 hover:bg-sky-100 hover:text-sky-900 ${className}`}
      title={title}
      aria-label={ariaLabel ?? title}
      onMouseDown={(e) => e.stopPropagation()}
      onDoubleClick={(e) => e.stopPropagation()}
      onClick={(e) => {
        e.stopPropagation();
        cancelTimers();
        openRef(refValue, query);
        // A click is a commitment: the pane stays when the pointer leaves.
        pinViewer();
      }}
      {...hoverProps}
    >
      <AnchorIcon size={size} strokeWidth={2.2} aria-hidden="true" />
      {preview}
    </button>
  );
}
