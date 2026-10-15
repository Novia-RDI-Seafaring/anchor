import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useRef, useState } from "react";

import { intents } from "@/api/intents";

export function SelectionAskDialog({ workspaceSlug, targetIds, onClose }: {
  workspaceSlug: string;
  targetIds: string[];
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const completed = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const submit = async () => {
    const trimmed = text.trim();
    if (!trimmed || targetIds.length === 0 || inFlight.current || completed.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      await intents.create({ text: trimmed, workspaceSlug, targets: targetIds });
      completed.current = true;
      if (mounted.current) setSent(true);
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : "Request failed. Try again.");
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  };

  if (targetIds.length === 0) return null;
  const scope = `${targetIds.length} selected ${targetIds.length === 1 ? "node" : "nodes"}`;
  return (
    <Dialog.Root open onOpenChange={(open) => { if (!open && !inFlight.current) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/20" onPointerDown={(e) => e.stopPropagation()} />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-neutral-200 bg-white p-4 shadow-xl"
          onPointerDown={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
          onEscapeKeyDown={(e) => { e.stopPropagation(); if (inFlight.current) e.preventDefault(); }}
          onInteractOutside={(e) => { if (inFlight.current) e.preventDefault(); }}
        >
          <Dialog.Title className="text-sm font-semibold text-neutral-900">Ask agent</Dialog.Title>
          <Dialog.Description className="mt-1 text-xs text-neutral-600">About {scope}.</Dialog.Description>
          {sent ? (
            <>
              <p role="status" className="mt-4 text-sm text-neutral-700">Request queued for {scope}. Follow it in Intents.</p>
              <button type="button" className="mt-4 rounded border px-3 py-1.5 text-xs" onClick={onClose}>Done</button>
            </>
          ) : (
            <form className="mt-4 space-y-3" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
              <label className="block text-xs text-neutral-700">
                Your request
                <textarea
                  autoFocus
                  value={text}
                  disabled={busy}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                      e.preventDefault();
                      void submit();
                    }
                  }}
                  rows={4}
                  className="mt-1 block w-full resize-y rounded border border-neutral-300 px-2 py-1.5 text-sm"
                />
              </label>
              <p className="text-[11px] text-neutral-500">Enter sends. Shift+Enter adds a line.</p>
              {error ? <p role="alert" className="text-xs text-red-700">Could not send request: {error}</p> : null}
              <div className="flex justify-end gap-2">
                <button type="button" disabled={busy} className="rounded border px-3 py-1.5 text-xs disabled:opacity-40" onClick={onClose}>Cancel</button>
                <button type="submit" disabled={busy || !text.trim()} className="rounded bg-neutral-900 px-3 py-1.5 text-xs text-white disabled:opacity-40">{busy ? "Sending..." : "Send to agent"}</button>
              </div>
            </form>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
