import type { WorkspaceListEntry } from "@/api/canvases";

export function indexBySlug(
  items: WorkspaceListEntry[],
): Map<string, WorkspaceListEntry> {
  const index = new Map<string, WorkspaceListEntry>();
  for (const item of items) index.set(item.slug, item);
  return index;
}

/** Select real roots and one stable representative for each rootless cycle. */
export function pickRoots(items: WorkspaceListEntry[]): string[] {
  const index = indexBySlug(items);
  const orphans = items
    .filter((item) => item.referenced_by.length === 0)
    .map((item) => item.slug);
  const orphanSet = new Set(orphans);
  const visited = new Set<string>();
  const cycleRoots: string[] = [];

  for (const item of items) {
    if (visited.has(item.slug)) continue;
    const stack = [item.slug];
    const component: string[] = [];
    let touchesOrphan = false;

    while (stack.length > 0) {
      const current = stack.pop()!;
      if (visited.has(current)) continue;
      visited.add(current);
      component.push(current);
      if (orphanSet.has(current)) touchesOrphan = true;

      const node = index.get(current);
      if (!node) continue;
      for (const child of node.references) {
        if (!visited.has(child)) stack.push(child);
      }
      for (const parent of node.referenced_by) {
        if (!visited.has(parent)) stack.push(parent);
      }
    }

    if (!touchesOrphan && component.length > 0) {
      component.sort();
      const representative = component[0];
      if (representative) cycleRoots.push(representative);
    }
  }

  return [...orphans, ...cycleRoots].sort();
}
