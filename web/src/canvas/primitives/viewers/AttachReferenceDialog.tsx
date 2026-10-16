import * as Dialog from "@radix-ui/react-dialog";
import { useRef, useState } from "react";

import { canvases } from "@/api/canvases";
import { references } from "@/api/references";
import { formatReferenceHref } from "@/canvas/anchorHref";
import { useCanvasStore, type Reference } from "@/stores/canvasStore";

export function AttachReferenceDialog({ canvasSlug, nodeId, reference, onClose }: {
  canvasSlug: string;
  nodeId: string;
  reference: Reference;
  onClose: () => void;
}) {
  const node = useCanvasStore((state) => state.slug === canvasSlug ? state.nodes[nodeId] : undefined);
  const [target, setTarget] = useState("node");
  const [originalText] = useState(typeof node?.data?.text === "string" ? node.data.text : "");
  const [rows] = useState<unknown[]>(() => Array.isArray(node?.data?.rows) ? structuredClone(node.data.rows) : []);
  const [selection, setSelection] = useState<[number, number]>([0, 0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const canCite = !!node && ["fact", "note", "text", "markdown"].includes(node.node_type) && !!originalText;
  const unavailable = !node || !!node.locked;

  const attach = async () => {
    if (inFlight.current || unavailable) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      // Re-read before writing: a remote edit must not be replaced by this dialog's old text.
      const state = useCanvasStore.getState();
      const current = state.slug === canvasSlug ? state.nodes[nodeId] : undefined;
      if (!current || current.locked) throw new Error("The target is missing or locked. Select an editable node.");
      if (target === "text") {
        if (!state.references.some((item) => item.id === reference.id)) throw new Error("The reference was deleted. Choose an existing reference.");
        if (current.data?.text !== originalText) throw new Error("The text changed. Cancel and select the words again.");
        const [start, end] = selection;
        if (start === end) throw new Error("Select the words to cite first.");
        // Do not nest a link inside an existing citation or another Markdown link.
        const links = originalText.matchAll(/\[((?:\\.|[^\]\\])*)\]\([^)]*\)/g);
        for (const link of links) {
          if (start < link.index + link[0].length && end > link.index) {
            throw new Error("Select words outside an existing link.");
          }
        }
        const label = originalText.slice(start, end).replace(/[\\[\]]/g, "\\$&");
        const text = `${originalText.slice(0, start)}[${label}](${formatReferenceHref(reference.id)})${originalText.slice(end)}`;
        await canvases.patchNode(canvasSlug, nodeId, { data: { text } });
      } else {
        if (target.startsWith("row:")) {
          const index = Number(target.slice(4));
          const currentRows = current.data?.rows;
          if (!Array.isArray(currentRows) || JSON.stringify(currentRows[index]) !== JSON.stringify(rows[index])) {
            throw new Error("The row changed. Cancel and select the row again.");
          }
        }
        await references.attach(canvasSlug, reference.id, {
          node_id: nodeId,
          ...(target.startsWith("row:") ? { row_index: Number(target.slice(4)) } : {}),
        });
      }
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not attach reference. Try again.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return <Dialog.Root open onOpenChange={(open) => { if (!open && !inFlight.current) onClose(); }}>
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-50 bg-black/20" />
      <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(30rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-neutral-200 bg-white p-4 shadow-xl"
        onPointerDown={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}
        onEscapeKeyDown={(event) => { if (inFlight.current) event.preventDefault(); }}
        onInteractOutside={(event) => { if (inFlight.current) event.preventDefault(); }}>
        <Dialog.Title className="text-sm font-semibold">Attach reference</Dialog.Title>
        <Dialog.Description className="mt-1 text-xs text-neutral-600">
          Use {reference.label || reference.source_ref.slug} on {node?.label || nodeId}.
        </Dialog.Description>
        <form className="mt-3 space-y-3" onSubmit={(event) => { event.preventDefault(); void attach(); }}>
          <label className="block text-xs">Attach to
            <select className="mt-1 block w-full rounded border p-1.5" value={target} disabled={busy || unavailable}
              onChange={(event) => setTarget(event.target.value)}>
              <option value="node">Whole node</option>
              {rows.map((row, index) => <option key={index} value={`row:${index}`}>Row {index + 1}: {String((row as { key?: unknown })?.key ?? "Untitled")}</option>)}
              {canCite ? <option value="text">Selected words in text</option> : null}
            </select>
          </label>
          {target === "text" ? <label className="block text-xs">Select the words to cite
            <textarea readOnly value={originalText} rows={5} disabled={busy}
              className="mt-1 block w-full resize-y rounded border p-2 text-sm"
              onSelect={(event) => setSelection([event.currentTarget.selectionStart, event.currentTarget.selectionEnd])} />
          </label> : <p className="text-xs text-neutral-500">This replaces the source attached to this target. Checking the source remains a separate step.</p>}
          {unavailable ? <p role="alert" className="text-xs text-red-700">The target is missing or locked. Select an editable node.</p> : null}
          {error ? <p role="alert" className="text-xs text-red-700">{error}</p> : null}
          <div className="flex justify-end gap-2">
            <button type="button" className="rounded border px-3 py-1.5 text-xs" disabled={busy} onClick={onClose}>Cancel</button>
            <button type="submit" className="rounded bg-neutral-900 px-3 py-1.5 text-xs text-white disabled:opacity-40"
              disabled={busy || unavailable || (target === "text" && selection[0] === selection[1])}>{busy ? "Attaching..." : "Attach"}</button>
          </div>
        </form>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
