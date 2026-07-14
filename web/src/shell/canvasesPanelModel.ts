import type { WorkspaceListEntry } from "@/api/canvases";

/** Exclude the current canvas and canvases already linked from it. */
export function filterAttachable(
  items: WorkspaceListEntry[],
  currentSlug: string,
): WorkspaceListEntry[] {
  const current = items.find((item) => item.slug === currentSlug);
  const alreadyLinked = new Set<string>(current?.references ?? []);
  return items.filter(
    (item) => item.slug !== currentSlug && !alreadyLinked.has(item.slug),
  );
}
