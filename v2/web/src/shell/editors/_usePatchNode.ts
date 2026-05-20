/**
 * usePatchNode — small debounced PATCH helper shared by Properties panel
 * editors.
 *
 * Calls `canvases.patchNode(workspaceSlug, nodeId, fields)` 300ms after the
 * last `patch(fields)` call. The fields argument shallow-merges into the
 * pending body so a flurry of edits across different fields lands as one
 * request. Surfaces the last error so the editor can render an inline
 * banner; the user's local input state stays dirty on failure so nothing
 * is lost.
 *
 * No "saving..." indicator yet — autosave is fast enough that one would
 * just flicker. Add when slow networks become a regular case.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { canvases } from "@/api/canvases";

type PatchBody = Record<string, unknown>;

export function usePatchNode(workspaceSlug: string, nodeId: string) {
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<PatchBody>({});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flush = useCallback(async () => {
    const body = pending.current;
    pending.current = {};
    timer.current = null;
    if (!workspaceSlug || !nodeId) return;
    if (Object.keys(body).length === 0) return;
    try {
      await canvases.patchNode(workspaceSlug, nodeId, body);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [workspaceSlug, nodeId]);

  const patch = useCallback((fields: PatchBody) => {
    pending.current = { ...pending.current, ...fields };
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => { void flush(); }, 300);
  }, [flush]);

  // Best-effort flush on unmount so closing the panel mid-edit doesn't
  // drop the trailing change.
  useEffect(() => {
    return () => {
      if (timer.current) {
        clearTimeout(timer.current);
        void flush();
      }
    };
  }, [flush]);

  // Reset the error banner when the user navigates to a different node.
  useEffect(() => { setError(null); }, [nodeId]);

  return { patch, error };
}
