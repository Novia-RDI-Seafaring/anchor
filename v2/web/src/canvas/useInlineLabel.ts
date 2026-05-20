/**
 * useInlineLabel — generic inline rename for any placed node.
 *
 * Shapes (`concept`, `entity`, `funnel`, `area`) and cards (`fact`, `note`)
 * embed this to expose double-click-to-edit on their label area. The hook
 * keeps an in-flight `value` separate from the canonical `label` prop so
 * users can backspace through the input without committing until they
 * blur or press Enter.
 *
 * Commit flow:
 *   beginEdit()   → enters edit mode, seeds the input with current label
 *   commit()      → PATCHes the node via canvases.updateNode/patchNode;
 *                   trims whitespace; bails out cleanly if the label
 *                   didn't change. Server echoes back via SSE so the
 *                   store-driven label stays the source of truth.
 *   cancel()      → exits edit mode without touching the server
 *
 * Auto-grown via:
 *   - inputProps.onKeyDown   (Enter commits, Escape cancels)
 *   - inputProps.onBlur      (commits — natural "tab away" behaviour)
 *   - inputProps.className   (carries `nodrag` so ReactFlow doesn't
 *                             intercept caret-positioning clicks; same
 *                             trick the document primitive uses)
 *
 * Empty labels are allowed. A pure shape with no label is the user's
 * starting state on every drag-out from the toolbar.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { canvases } from "@/api/canvases";

type Options = {
  /** Canvas workspace slug — required to PATCH the node. */
  workspaceSlug: string;
  /** Node id this hook operates on. */
  nodeId: string;
  /** Canonical label coming from the canvas store. */
  label: string;
};

type InputProps = {
  value: string;
  onChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLInputElement>) => void;
  onBlur: () => void;
  onMouseDown: (event: React.MouseEvent<HTMLInputElement>) => void;
  className: string;
  ref: React.RefObject<HTMLInputElement | null>;
};

type Result = {
  /** True when the label is currently being edited. */
  editing: boolean;
  /** Current in-flight value (use for the <input value={...}>). */
  value: string;
  /** Enter edit mode. */
  beginEdit: () => void;
  /** Commit the in-flight value to the server. */
  commit: () => void;
  /** Discard edits and exit edit mode. */
  cancel: () => void;
  /** Pre-wired props for an `<input>` element. */
  inputProps: InputProps;
};

export function useInlineLabel({ workspaceSlug, nodeId, label }: Options): Result {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(label);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Reset the in-flight value whenever the canonical label changes from
  // the outside (SSE echo of a successful commit, or a remote edit landed).
  useEffect(() => {
    if (!editing) setValue(label);
  }, [label, editing]);

  // Focus + select the field as soon as we enter edit mode. select-on-edit
  // matches what every native rename UX does — easier to overwrite than
  // to backspace through a long name.
  useEffect(() => {
    if (!editing) return;
    const el = inputRef.current;
    if (!el) return;
    el.focus();
    el.select();
  }, [editing]);

  const beginEdit = useCallback(() => {
    setValue(label);
    setEditing(true);
  }, [label]);

  const cancel = useCallback(() => {
    setValue(label);
    setEditing(false);
  }, [label]);

  const commit = useCallback(() => {
    setEditing(false);
    const next = value.trim();
    if (next === label.trim()) return;  // no-op when unchanged
    canvases.patchNode(workspaceSlug, nodeId, { label: next }).catch((err) => {
      // eslint-disable-next-line no-console
      console.error("inline rename failed", err);
    });
  }, [value, label, workspaceSlug, nodeId]);

  const inputProps: InputProps = {
    value,
    onChange: (event) => setValue(event.target.value),
    onKeyDown: (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        commit();
      } else if (event.key === "Escape") {
        event.preventDefault();
        cancel();
      }
      // Stop ReactFlow from hijacking keystrokes (delete-on-Backspace etc.).
      event.stopPropagation();
    },
    onBlur: commit,
    // Prevent the click from bubbling up to ReactFlow's node-drag handler;
    // without this the caret jumps when the user clicks inside the input.
    onMouseDown: (event) => event.stopPropagation(),
    className: "nodrag",
    ref: inputRef,
  };

  return { editing, value, beginEdit, commit, cancel, inputProps };
}
