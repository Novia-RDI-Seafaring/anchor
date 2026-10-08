/**
 * nodeDiff.ts — what a proposal actually changed.
 *
 * Structural, not visual. Comparing two rendered pictures tells you THAT
 * something differs and flags antialiasing while it is at it; comparing the
 * data tells you which row, which value, which field. Since a spec row is a
 * row on screen, the structural answer maps straight onto what the reader
 * sees, and the highlight can land on the cell that moved.
 *
 * Deliberately shallow on rows. A spec's rows are the thing a reader reviews,
 * so they are diffed by position and reported per field, rather than folded
 * into one "rows changed".
 */

export type FieldChange = {
  field: string;
  before: unknown;
  after: unknown;
};

export type RowChange = {
  index: number;
  kind: "added" | "removed" | "changed";
  /** Which of key / value / source_ref / review differ. */
  fields: string[];
  before?: Record<string, unknown>;
  after?: Record<string, unknown>;
};

export type NodeDiff = {
  fields: FieldChange[];
  rows: RowChange[];
  /** Nothing differs: the proposal touched this element without changing it. */
  unchanged: boolean;
};

/** Fields whose change is about position rather than content. */
export const GEOMETRY_FIELDS = ["x", "y", "width", "height"] as const;

const ROW_FIELDS = ["key", "value", "source_ref", "review", "evidence"] as const;

function same(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a === undefined || b === undefined || a === null || b === null) return false;
  if (typeof a !== "object" || typeof b !== "object") return false;
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * Compare a node's stored data before and after a proposal.
 *
 * `before` carries only the fields the proposal captured, so a field absent
 * from it is one the proposal did not touch -- not one that was empty. That
 * distinction matters: treating every absent field as a change would paint
 * the whole card as edited.
 */
export function diffNodeData(
  before: Record<string, unknown> | null | undefined,
  after: Record<string, unknown> | null | undefined,
): NodeDiff {
  const b = before ?? {};
  const a = after ?? {};
  const fields: FieldChange[] = [];
  for (const key of Object.keys(b)) {
    if (key === "rows") continue;
    if (!same(b[key], a[key])) fields.push({ field: key, before: b[key], after: a[key] });
  }
  return {
    fields,
    rows: diffRows(b.rows as Row[] | undefined, a.rows as Row[] | undefined),
    unchanged:
      fields.length === 0 && diffRows(b.rows as Row[] | undefined, a.rows as Row[] | undefined).length === 0,
  };
}

type Row = Record<string, unknown>;

/** Rows compared by position: a spec's order is part of what it means. */
export function diffRows(before: Row[] | undefined, after: Row[] | undefined): RowChange[] {
  if (!before && !after) return [];
  const b = before ?? [];
  const a = after ?? [];
  // `before` without rows means the proposal did not touch them.
  if (!before) return [];
  const out: RowChange[] = [];
  for (let i = 0; i < Math.max(b.length, a.length); i++) {
    const rb = b[i];
    const ra = a[i];
    if (rb && !ra) {
      out.push({ index: i, kind: "removed", fields: [], before: rb });
      continue;
    }
    if (!rb && ra) {
      out.push({ index: i, kind: "added", fields: [], after: ra });
      continue;
    }
    if (!rb || !ra) continue;
    const changed = ROW_FIELDS.filter((f) => !same(rb[f], ra[f]));
    if (changed.length > 0) {
      out.push({ index: i, kind: "changed", fields: [...changed], before: rb, after: ra });
    }
  }
  return out;
}

/**
 * How many separate things changed, for choosing how to show it.
 *
 * One changed value reads better inline -- old struck through, new beside it,
 * the way a tracked change does. Several read better side by side. The count
 * decides, rather than the reader having to pick a view.
 */
export function changeCount(diff: NodeDiff): number {
  return diff.fields.length + diff.rows.length;
}

/** True when everything that changed is about where the element sits. */
export function onlyGeometry(diff: NodeDiff): boolean {
  return (
    diff.rows.length === 0 &&
    diff.fields.length > 0 &&
    diff.fields.every((f) => (GEOMETRY_FIELDS as readonly string[]).includes(f.field))
  );
}
