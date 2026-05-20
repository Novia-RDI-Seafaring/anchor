/**
 * useInlineLabel — legacy single-line label edit, now a thin shim over the
 * generalised `useInlineField` hook.
 *
 * Kept as a back-compat entry point so shape components don't all need to
 * shift their imports. For new code prefer `useInlineField` directly — it
 * supports both single-line labels (the original behaviour) and multi-line
 * body text via `multiline: true`.
 *
 * Behaviour preserved exactly:
 *   - Enter commits, Esc cancels, blur commits.
 *   - Trims whitespace on commit; no-op when unchanged.
 *   - `className` carries `nodrag`; click bubbling is stopped so the caret
 *     doesn't fight ReactFlow's node-drag handler.
 */
import { useInlineField } from "./useInlineField";

type Options = {
  /** Canvas workspace slug — required to PATCH the node. */
  workspaceSlug: string;
  /** Node id this hook operates on. */
  nodeId: string;
  /** Canonical label coming from the canvas store. */
  label: string;
};

export function useInlineLabel({ workspaceSlug, nodeId, label }: Options) {
  return useInlineField({
    workspaceSlug,
    nodeId,
    value: label,
    field: "label",
    multiline: false,
  });
}
