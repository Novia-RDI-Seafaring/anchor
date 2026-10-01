import type { ResolvableRef } from "@/api/documents";
import { describeRef } from "@/canvas/anchorHref";
import { SourceAnchorButton } from "@/canvas/SourceAnchorButton";
import { useUiStore } from "@/stores/uiStore";

/** Node-level provenance stays visible even when no document card is placed. */
export function NodeSourceBadge({
  data,
  workspaceSlug,
}: {
  data: Record<string, unknown>;
  workspaceSlug: string | undefined;
}) {
  const clearHovered = useUiStore((state) => state.clearHoveredSourceRef);
  const ref = data.source_ref as ResolvableRef | null | undefined;
  if (typeof ref?.slug !== "string" || !ref.slug.trim()
    || typeof ref.page !== "number" || !Number.isInteger(ref.page) || ref.page < 1) return null;

  const description = describeRef(ref);
  return (
    <div
      className="absolute -bottom-3 left-2 z-10 max-w-[calc(100%-1rem)]"
      onMouseLeave={clearHovered}
    >
      <SourceAnchorButton
        workspaceSlug={workspaceSlug}
        refValue={ref}
        title={`Open source: ${description}`}
        ariaLabel={`Open source: ${description}`}
        className="h-6 max-w-full border border-sky-300 bg-white px-1.5 text-[10px] shadow-sm"
      >
        <span className="min-w-0 truncate">{ref.slug}</span>
        <span className="shrink-0">p. {ref.page}</span>
      </SourceAnchorButton>
    </div>
  );
}
