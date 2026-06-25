/**
 * useInlineField - generic inline edit for any string-valued field on a node.
 *
 * Powers both single-line label edits (shapes, cards) and multi-line body
 * edits (notes). The hook is field-agnostic: `field: "label"` patches the
 * canonical node label, `field: "text"` (or any other string) patches the
 * matching property inside `data`. Server echoes back via SSE; the
 * store-driven value remains the source of truth.
 *
 * Commit flow (identical to the predecessor):
 *   beginEdit()   -> enters edit mode, seeds the input with the current value
 *   commit()      -> PATCHes the node (label = top-level, anything else = data);
 *                   bails out cleanly when the value didn't change.
 *   cancel()      -> exits edit mode without touching the server.
 *
 * Auto-grown via `inputProps`:
 *   - onChange  - store the in-flight value
 *   - onKeyDown - Enter commits (multi-line: Shift+Enter inserts a newline,
 *                 Enter alone commits); Escape cancels; keystrokes are
 *                 stopPropagation'd so ReactFlow doesn't hijack Delete/Backspace.
 *   - onBlur    - commits (natural "tab away" behaviour)
 *   - onMouseDown - stopPropagation so the click doesn't reach ReactFlow's
 *                   node-drag handler; without this the caret jumps.
 *   - className - carries `nodrag` so ReactFlow doesn't intercept caret
 *                 positioning.
 *
 * Empty values are allowed. A pure shape with no label is the starting
 * state on every drag-out from the tool rail.
 *
 * Multi-line specifics: when `multiline: true` the hook returns
 * `inputProps` shaped for a `<textarea>`. The component is responsible for
 * auto-resizing — we provide a `textareaRef` to make that easy.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { canvases } from "@/api/canvases";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

type Options = {
  /** Canvas workspace slug — required to PATCH the node. */
  workspaceSlug: string;
  /** Node id this hook operates on. */
  nodeId: string;
  /** Canonical current value of the field. */
  value: string;
  /**
   * Which field this hook edits. `"label"` patches the top-level node
   * label; any other string patches `data.<field>`.
   */
  field?: "label" | "text" | string;
  /** When true the hook drives a `<textarea>` and allows newlines. */
  multiline?: boolean;
  /**
   * When false, `beginEdit()` is a no-op. draw.io-style selection model:
   * a node must be selected before its label/body becomes editable, so
   * shapes/cards pass `canEdit={selected}`. Defaults to true for backwards
   * compatibility — older callers pre-selection-gating still work.
   */
  canEdit?: boolean;
};

type SingleLineInputProps = {
  value: string;
  onChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLInputElement>) => void;
  onBlur: () => void;
  onMouseDown: (event: React.MouseEvent<HTMLInputElement>) => void;
  className: string;
  ref: React.RefObject<HTMLInputElement | null>;
};

type MultiLineInputProps = {
  value: string;
  onChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onBlur: () => void;
  onMouseDown: (event: React.MouseEvent<HTMLTextAreaElement>) => void;
  className: string;
  ref: React.RefObject<HTMLTextAreaElement | null>;
  rows: number;
};

type Result<M extends boolean> = {
  /** True when the value is currently being edited. */
  editing: boolean;
  /** Current in-flight value (use for the `<input>`/`<textarea>` `value`). */
  value: string;
  /** Enter edit mode. */
  beginEdit: () => void;
  /** Commit the in-flight value to the server. */
  commit: () => void;
  /** Discard edits and exit edit mode. */
  cancel: () => void;
  /** Pre-wired props for the input element. */
  inputProps: M extends true ? MultiLineInputProps : SingleLineInputProps;
};

export function useInlineField<M extends boolean = false>({
  workspaceSlug,
  nodeId,
  value: canonicalValue,
  field = "label",
  multiline,
  canEdit = true,
}: Options & { multiline?: M }): Result<M> {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(canonicalValue);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Reset the in-flight value whenever the canonical value changes from
  // the outside (SSE echo of a successful commit, or a remote edit landed).
  useEffect(() => {
    if (!editing) setValue(canonicalValue);
  }, [canonicalValue, editing]);

  // When the node becomes deselected mid-edit (`canEdit` flips to false),
  // commit any pending change rather than silently discarding it. This is
  // the draw.io rule: click-outside both deselects and commits.
  const editingRef = useRef(editing);
  const valueRef = useRef(value);
  editingRef.current = editing;
  valueRef.current = value;
  useEffect(() => {
    if (canEdit) return;
    if (!editingRef.current) return;
    setEditing(false);
    const next = multiline
      ? valueRef.current.replace(/\s+$/g, "")
      : valueRef.current.trim();
    const canonical = multiline
      ? canonicalValue.replace(/\s+$/g, "")
      : canonicalValue.trim();
    if (next === canonical) return;
    // For non-label fields, merge with the current `data` snapshot before
    // patching. The server replaces `data` whole, so a naive
    // `{ data: { [field]: next } }` would wipe every other key — most
    // notably `canvas_slug` on a sub-canvas tile, which then breaks the
    // CanvasListPage / CanvasTree builder.
    const body: Record<string, unknown> = field === "label"
      ? { label: next }
      : { data: { ...(useCanvasStore.getState().nodes[nodeId]?.data ?? {}), [field]: next } };
    canvases.patchNode(workspaceSlug, nodeId, body).catch((err) => {
      // eslint-disable-next-line no-console
      console.error(`inline ${field} edit failed`, err);
    });
  }, [canEdit, canonicalValue, multiline, field, nodeId, workspaceSlug]);

  // Focus + select the field as soon as we enter edit mode. select-on-edit
  // matches what every native rename UX does — easier to overwrite than
  // to backspace through a long name. For multi-line we focus but don't
  // select-all (selecting whole bodies is unexpected).
  useEffect(() => {
    if (!editing) return;
    if (multiline) {
      const el = textareaRef.current;
      if (!el) return;
      el.focus();
      // Place caret at end — feels closer to "click to edit" than overwrite.
      const end = el.value.length;
      try {
        el.setSelectionRange(end, end);
      } catch {
        // Some browsers throw on hidden elements; ignore.
      }
    } else {
      const el = inputRef.current;
      if (!el) return;
      el.focus();
      el.select();
    }
  }, [editing, multiline]);

  const beginEdit = useCallback(() => {
    // draw.io rule: a node must be selected before its label/body is
    // editable. Callers gate via `canEdit={selected}`; the older single-
    // hook callers default to `canEdit: true` to preserve behaviour.
    if (!canEdit) return;
    setValue(canonicalValue);
    setEditing(true);
  }, [canonicalValue, canEdit]);

  // Quick-add coordination: when `DirectionalConnectors` or
  // `QuickAddPopover` mints a new node, they stamp the new id into
  // `useUiStore.pendingInlineRenameNodeId`. We're the natural consumer
  // because every shape primitive that owns a label mounts a
  // `useInlineField({ field: "label" })` — centralising the auto-focus
  // here avoids editing each shape file. Gated on `field === "label"` so
  // body-editor hooks on the same node don't race for focus.
  const pendingRenameId = useUiStore((s) => s.pendingInlineRenameNodeId);
  useEffect(() => {
    if (field !== "label") return;
    if (!canEdit) return;
    if (pendingRenameId !== nodeId) return;
    const consumed = useUiStore.getState().consumeInlineRename(nodeId);
    if (!consumed) return;
    setValue(canonicalValue);
    setEditing(true);
  }, [pendingRenameId, nodeId, field, canEdit, canonicalValue]);

  const cancel = useCallback(() => {
    setValue(canonicalValue);
    setEditing(false);
  }, [canonicalValue]);

  const commit = useCallback(() => {
    setEditing(false);
    // Trim trailing whitespace only for single-line fields; for multi-line
    // body text the user may legitimately want trailing newlines (rare) so
    // we trim both ends conservatively.
    const next = multiline ? value.replace(/\s+$/g, "") : value.trim();
    const canonical = multiline ? canonicalValue.replace(/\s+$/g, "") : canonicalValue.trim();
    if (next === canonical) return; // no-op
    const body: Record<string, unknown> = field === "label"
      ? { label: next }
      : { data: { ...(useCanvasStore.getState().nodes[nodeId]?.data ?? {}), [field]: next } };
    canvases.patchNode(workspaceSlug, nodeId, body).catch((err) => {
      // eslint-disable-next-line no-console
      console.error(`inline ${field} edit failed`, err);
    });
  }, [value, canonicalValue, workspaceSlug, nodeId, field, multiline]);

  const handleKey = (
    event:
      | React.KeyboardEvent<HTMLInputElement>
      | React.KeyboardEvent<HTMLTextAreaElement>,
  ) => {
    if (event.key === "Enter") {
      // Multi-line: Shift+Enter inserts a newline, plain Enter commits.
      // Single-line: any Enter commits.
      if (multiline && event.shiftKey) {
        // Fall through to default — let the textarea insert the newline.
        event.stopPropagation();
        return;
      }
      event.preventDefault();
      commit();
    } else if (event.key === "Escape") {
      event.preventDefault();
      cancel();
    }
    // Stop ReactFlow from hijacking keystrokes (delete-on-Backspace etc.).
    event.stopPropagation();
  };

  if (multiline) {
    const props: MultiLineInputProps = {
      value,
      onChange: (event) => setValue(event.target.value),
      onKeyDown: handleKey,
      onBlur: commit,
      onMouseDown: (event) => event.stopPropagation(),
      className: "nodrag",
      ref: textareaRef,
      rows: Math.max(2, value.split("\n").length),
    };
    return {
      editing,
      value,
      beginEdit,
      commit,
      cancel,
      inputProps: props as Result<M>["inputProps"],
    };
  }

  const props: SingleLineInputProps = {
    value,
    onChange: (event) => setValue(event.target.value),
    onKeyDown: handleKey,
    onBlur: commit,
    onMouseDown: (event) => event.stopPropagation(),
    className: "nodrag",
    ref: inputRef,
  };
  return {
    editing,
    value,
    beginEdit,
    commit,
    cancel,
    inputProps: props as Result<M>["inputProps"],
  };
}
