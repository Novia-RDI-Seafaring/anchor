import { Anchor } from "lucide-react";

import type { ResolvableRef } from "@/api/documents";
import { describeRef } from "@/canvas/anchorHref";
import { useOpenSourceRef } from "@/canvas/useOpenSourceRef";
import { useUiStore } from "@/stores/uiStore";

/**
 * SourceRefLink — the words, then the anchor.
 *
 * An `anchor:` link inside prose renders as the text it wrapped with a
 * small anchor glyph after it. Clicking opens the document at that page
 * and highlights the region, the same landing a spec row gives you.
 * Hovering broadcasts the ref, so a document card already on the canvas
 * lights up the region under the cursor without anything being clicked.
 *
 * A ref that names no document or no page renders struck through, in the
 * colour of a problem, and says so on hover. A pointer that goes nowhere
 * is a mistake worth seeing rather than prose that quietly reads as if
 * it were sourced.
 */
export function SourceRefLink({
  workspaceSlug,
  refValue,
  children,
}: {
  workspaceSlug: string | undefined;
  /** Parsed ref, or `null` when the `anchor:` target was malformed. */
  refValue: ResolvableRef | null;
  children?: React.ReactNode;
}) {
  const openRef = useOpenSourceRef(workspaceSlug);
  const setHovered = useUiStore((s) => s.setHoveredSourceRef);
  const clearHovered = useUiStore((s) => s.clearHoveredSourceRef);

  if (!refValue) {
    return (
      <span
        className="cursor-help text-rose-600 line-through decoration-rose-300"
        title="This source link names no document or no page, so it points nowhere."
        data-testid="source-ref-broken"
      >
        {children}
      </span>
    );
  }

  const text = typeof children === "string" ? children : undefined;
  return (
    <button
      type="button"
      className="nodrag inline items-baseline rounded-sm text-sky-700 underline decoration-sky-300 underline-offset-2 hover:decoration-sky-600"
      title={`Open ${describeRef(refValue)}`}
      data-testid="source-ref-link"
      onClick={(event) => {
        event.stopPropagation();
        openRef(refValue, text);
      }}
      onMouseEnter={() =>
        setHovered({
          slug: refValue.slug ?? "",
          page: refValue.page ?? 1,
          region_id: refValue.region_id,
          bbox: refValue.bbox,
          item_id: refValue.item_id,
          cell: refValue.cell,
        })
      }
      onMouseLeave={() => clearHovered()}
    >
      {children}
      <Anchor
        className="ml-0.5 inline size-[0.85em] -translate-y-[0.05em] stroke-sky-500"
        aria-label="source"
      />
    </button>
  );
}
