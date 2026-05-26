/**
 * CanvasTree — render the canvas-reference graph as a collapsible folder tree.
 *
 * Input: the `WorkspaceListEntry[]` returned by `canvases.list()` (the
 * envelope with `node_count` / `edge_count` / `references` /
 * `referenced_by`). The component derives:
 *
 *   - `roots` — canvases whose `referenced_by` is empty (true roots) or
 *     whose only referrers form a cycle they're a member of (so the
 *     cycle root surfaces somewhere in the tree).
 *   - children of a slug = `entry.references` for that slug.
 *
 * Rules for the visual:
 *   - A canvas referenced by ≥2 parents appears under each parent — we
 *     render the DAG honestly. A small `↔ N` badge next to its title
 *     disambiguates: "this canvas is also reachable from N other places".
 *   - A canvas that re-references one of its ancestors (cycle) shows a
 *     `↩ cycle` chip and does NOT recurse below itself. The recursion
 *     stack is tracked via the `ancestors` set passed down each level.
 *   - Click chevron to expand/collapse. Click title or folder icon to
 *     navigate to `/c/<slug>`.
 *
 * Deliberately no third-party tree library — a recursive component with
 * a `level` prop and a `useState<Set<string>>` for expanded slugs is
 * plenty. The tree is read-only (no drag-to-reparent, no multi-select).
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import type { WorkspaceListEntry } from "@/api/canvases";

export type CanvasTreeProps = {
  items: WorkspaceListEntry[];
};

/** Build the slug → entry index once per render. */
function indexBySlug(items: WorkspaceListEntry[]): Map<string, WorkspaceListEntry> {
  const out = new Map<string, WorkspaceListEntry>();
  for (const it of items) out.set(it.slug, it);
  return out;
}

/**
 * Determine which slugs are tree roots.
 *
 * - A canvas with `referenced_by.length === 0` is a root.
 * - A cycle with no external parent — every member's `referenced_by`
 *   only points to other members of the same cycle — would otherwise
 *   be invisible. Pick its lexicographically-smallest slug as the root
 *   so it still surfaces in the tree.
 */
export function pickRoots(items: WorkspaceListEntry[]): string[] {
  const index = indexBySlug(items);
  const orphans = items.filter((it) => it.referenced_by.length === 0).map((it) => it.slug);
  const orphanSet = new Set(orphans);

  // Connected-component sweep over the (references ∪ referenced_by) graph
  // treated as undirected for reachability. Every canvas reachable from
  // an orphan is already covered (an orphan ancestor will lead the tree
  // down to it via `references`). The interesting case is a connected
  // component with no orphan inside — a pure cycle that would otherwise
  // be invisible. Adopt its smallest slug as a synthetic root.
  const visited = new Set<string>();
  const extraRoots: string[] = [];
  for (const it of items) {
    if (visited.has(it.slug)) continue;
    const stack = [it.slug];
    const component: string[] = [];
    let touchesOrphan = false;
    while (stack.length > 0) {
      const cur = stack.pop()!;
      if (visited.has(cur)) continue;
      visited.add(cur);
      component.push(cur);
      if (orphanSet.has(cur)) touchesOrphan = true;
      const node = index.get(cur);
      if (!node) continue;
      for (const r of node.references) if (!visited.has(r)) stack.push(r);
      for (const r of node.referenced_by) if (!visited.has(r)) stack.push(r);
    }
    if (!touchesOrphan && component.length > 0) {
      // Adopt the smallest slug as the cycle-root.
      component.sort();
      const head = component[0];
      if (head) extraRoots.push(head);
    }
  }
  // Stable order: alphabetical for predictable rendering.
  return [...orphans, ...extraRoots].sort();
}

type RowProps = {
  slug: string;
  index: Map<string, WorkspaceListEntry>;
  level: number;
  ancestors: ReadonlySet<string>;
  expanded: Set<string>;
  toggle: (slug: string) => void;
};

function Row({ slug, index, level, ancestors, expanded, toggle }: RowProps) {
  const entry = index.get(slug);
  if (!entry) {
    // Dangling reference (target canvas was deleted). Render a tombstone
    // row so the user notices instead of silently hiding it.
    return (
      <li>
        <div
          className="flex items-center gap-2 rounded px-2 py-1 text-sm text-amber-700"
          style={{ paddingLeft: 8 + level * 18 }}
        >
          <span aria-hidden className="w-4 text-center">!</span>
          <span aria-hidden>?</span>
          <span className="italic">{slug}</span>
          <span className="text-xs text-amber-600">missing</span>
        </div>
      </li>
    );
  }

  const isCycle = ancestors.has(slug);
  const refs = isCycle ? [] : entry.references;
  const hasChildren = refs.length > 0;
  const isOpen = expanded.has(slug);
  const multiParent = entry.referenced_by.length > 1;
  // Children inherit the ancestor set + this slug.
  const childAncestors = new Set(ancestors);
  childAncestors.add(slug);

  return (
    <li>
      <div
        className="group flex items-center gap-1.5 rounded px-2 py-1.5 text-sm hover:bg-neutral-100"
        style={{ paddingLeft: 8 + level * 18 }}
      >
        {hasChildren ? (
          <button
            type="button"
            className="flex h-4 w-4 items-center justify-center text-neutral-500 hover:text-neutral-900"
            onClick={() => toggle(slug)}
            aria-label={isOpen ? "collapse" : "expand"}
            aria-expanded={isOpen}
          >
            <span className="text-[10px]">{isOpen ? "▼" : "▶"}</span>
          </button>
        ) : (
          <span aria-hidden className="inline-block h-4 w-4" />
        )}
        <Link
          to={`/c/${entry.slug}`}
          className="flex min-w-0 flex-1 items-baseline gap-2"
        >
          <span aria-hidden className="text-neutral-500">
            {hasChildren ? "\u{1F4C1}" : "\u{1F4C4}"}
          </span>
          <span className="truncate font-medium text-neutral-900 group-hover:underline">
            {entry.title || entry.slug}
          </span>
          <span className="truncate text-xs text-neutral-500">{entry.slug}</span>
          {multiParent ? (
            <span
              className="rounded-full border border-sky-300 bg-sky-50 px-1.5 text-[10px] font-medium text-sky-800"
              title={`also reachable from ${entry.referenced_by.length - 1} other place(s)`}
            >
              {"↔ "}
              {entry.referenced_by.length}
            </span>
          ) : null}
          {isCycle ? (
            <span
              className="rounded-full border border-amber-300 bg-amber-50 px-1.5 text-[10px] font-medium text-amber-800"
              title="cycle: this canvas re-references an ancestor"
            >
              {"↩ cycle"}
            </span>
          ) : null}
        </Link>
        <span className="ml-auto shrink-0 text-xs text-neutral-500">
          {entry.node_count} nodes &middot; {entry.edge_count} edges
        </span>
      </div>
      {hasChildren && isOpen ? (
        <ul role="group">
          {refs.map((child) => (
            <Row
              key={`${slug}->${child}`}
              slug={child}
              index={index}
              level={level + 1}
              ancestors={childAncestors}
              expanded={expanded}
              toggle={toggle}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function CanvasTree({ items }: CanvasTreeProps) {
  const index = useMemo(() => indexBySlug(items), [items]);
  const roots = useMemo(() => pickRoots(items), [items]);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  const toggle = (slug: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  };

  if (items.length === 0) {
    return (
      <div className="rounded border border-dashed border-neutral-300 p-6 text-center text-neutral-500">
        No canvases yet. Create one above.
      </div>
    );
  }

  return (
    <ul role="tree" className="space-y-0.5">
      {roots.map((slug) => (
        <Row
          key={slug}
          slug={slug}
          index={index}
          level={0}
          ancestors={new Set()}
          expanded={expanded}
          toggle={toggle}
        />
      ))}
    </ul>
  );
}
