import type { ReactNode } from "react";

import { parseAnchorHref, parseReferenceHref } from "@/canvas/anchorHref";
import { SourceRefLink } from "@/canvas/SourceRefLink";
import { useCanvasStore } from "@/stores/canvasStore";

/** Resolve a bibliography citation from the owning canvas's live snapshot. */
export function CitationLink({ href, workspaceSlug, children }: {
  href: string;
  workspaceSlug: string | undefined;
  children?: ReactNode;
}) {
  const referenceId = parseReferenceHref(href);
  const reference = useCanvasStore((state) => state.slug === workspaceSlug
    ? state.references.find((ref) => ref.id === referenceId) : undefined);
  return <SourceRefLink workspaceSlug={workspaceSlug}
    refValue={referenceId ? reference?.source_ref ?? null : parseAnchorHref(href)}
    quote={reference?.source_ref.detail?.quote}
    brokenReason={referenceId ? "This reference is missing from this canvas's bibliography." : undefined}>
    {children}
  </SourceRefLink>;
}
