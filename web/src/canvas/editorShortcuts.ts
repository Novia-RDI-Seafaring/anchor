import { isTextEditing } from "@/shared/clipboard";
import type { ClipboardNode } from "./clipboard";
import { parentedNodeIds, type NodeMove } from "./geometry";

export type EditorAction = { type: "rename"; nodeId: string } | { type: "duplicate" }
  | { type: "nudge"; nodeId: string; dx: number; dy: number };

/** Only canvas focus owns these keys. Text, source panes and controls keep theirs. */
export function editorAction(event: KeyboardEvent): EditorAction | null {
  if (event.defaultPrevented || event.altKey || isTextEditing(event.target)) return null;
  const target = event.target;
  if (!(target instanceof HTMLElement) || !target.closest(".react-flow")) return null;
  if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === "d") return { type: "duplicate" };
  if (event.ctrlKey || event.metaKey) return null;
  const node = target.closest<HTMLElement>(".react-flow__node");
  const nodeId = node?.dataset.id;
  if (!nodeId || target !== node) return null;
  if (event.key === "Enter" && !event.shiftKey) return { type: "rename", nodeId };
  const directions: Record<string, [number, number]> = {
    ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1],
  };
  const direction = directions[event.key];
  if (!direction) return null;
  const step = event.shiftKey ? 20 : 5;
  return { type: "nudge", nodeId, dx: direction[0] * step, dy: direction[1] * step };
}

const INLINE_RENAME_TYPES = new Set(["concept", "entity", "funnel", "area", "text", "fact", "note", "markdown", "spec", "section", "image", "canvas"]);
export function supportsInlineRename(type: string) { return INLINE_RENAME_TYPES.has(type); }

/** Stored coordinates are absolute. Moving a container moves each descendant once. */
export function planNudge(nodes: Record<string, ClipboardNode>, selected: string[], dx: number, dy: number): NodeMove[] {
  const roots = selected.filter((id) => nodes[id] && nodes[id].locked !== true && nodes[id].data?.locked !== true);
  return parentedNodeIds(nodes, roots).map((id) => ({ id, x: nodes[id]!.x + dx, y: nodes[id]!.y + dy }));
}
