import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { documents, refHasSelector, type ResolvableRef } from "@/api/documents";
import { intents, INTENTS_CHANGED_EVENT, type Intent } from "@/api/intents";
import { AnchoredText } from "@/canvas/AnchoredText";
import { NodePresentationEditor } from "@/canvas/NodePresentationEditor";
import { SourceAnchorButton } from "@/canvas/SourceAnchorButton";
import { evidenceLabels, evidenceState } from "@/canvas/evidence";
import { markdownComponents, urlTransform } from "@/canvas/shapes/MarkdownNode";
import { useOpenSourceRef } from "@/canvas/useOpenSourceRef";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function sourceRefFor(value: unknown, data: Record<string, unknown>, nodes: Record<string, { node_type: string; data?: Record<string, unknown> }>, documentId?: string): ResolvableRef | null {
  const ref = record(value);
  const docId = typeof ref.doc_id === "string" ? ref.doc_id : documentId;
  const candidate = docId ? nodes[docId] : undefined;
  const doc = candidate?.node_type === "document" ? candidate : undefined;
  const nodeRef = record(data.source_ref);
  const inheritedSlug = data.source_doc_slug ?? nodeRef.slug ?? doc?.data?.slug;
  const slug = ref.slug ?? inheritedSlug;
  if (typeof slug !== "string" || !slug.trim()) return null;
  const page = typeof ref.page === "number" && Number.isInteger(ref.page) && ref.page > 0;
  const region = ref.region_id ?? ref.source_region_id
    ?? (slug === inheritedSlug ? data.source_region_id ?? nodeRef.region_id : undefined);
  if (!page && !region && !ref.item_id) return null;
  return { ...ref, slug, region_id: region } as ResolvableRef;
}

export function intentTargetsNode(intent: Intent, workspaceSlug: string, nodeId: string) {
  return intent.targets?.some((target) => target.workspace_id === workspaceSlug && target.node_id === nodeId)
    || (intent.payload.node_id === nodeId && (intent.payload.workspace_id ?? intent.origin_canvas_id) === workspaceSlug)
    || (intent.target === nodeId && intent.origin_canvas_id === workspaceSlug);
}

export function NodeDetailPanel({ workspaceSlug, nodeId, onClose, readOnly = false }: {
  workspaceSlug: string; nodeId: string; onClose: () => void; readOnly?: boolean;
}) {
  const nodes = useCanvasStore((state) => state.nodes);
  const edges = useCanvasStore((state) => state.edges);
  const node = nodes[nodeId];
  const [threads, setThreads] = useState<Intent[]>([]);
  const [threadError, setThreadError] = useState(false);
  const setSelectedNodeId = useUiStore((state) => state.setSelectedNodeId);
  const setPropertiesOpen = useUiStore((state) => state.setPropertiesOpen);
  useEffect(() => {
    setThreads([]);
    setThreadError(false);
    let active = true;
    const load = () => void intents.listAll().then((all) => {
      if (!active) return;
      setThreads(all.filter((intent) => intentTargetsNode(intent, workspaceSlug, nodeId)));
      setThreadError(false);
    }).catch(() => { if (active) setThreadError(true); });
    load();
    window.addEventListener(INTENTS_CHANGED_EVENT, load);
    const timer = window.setInterval(load, 8000);
    return () => { active = false; window.removeEventListener(INTENTS_CHANGED_EVENT, load); window.clearInterval(timer); };
  }, [workspaceSlug, nodeId]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [onClose]);
  const data = node?.data ?? {};
  const rows = Array.isArray(data.rows) ? data.rows.map(record) : [];
  const evidence = Object.values(edges).filter((edge) => edge.data?.kind === "evidence" && edge.source === nodeId);
  const refs = useMemo(() => {
    const found: ResolvableRef[] = [];
    const add = (value: unknown, documentId?: string) => {
      const normalized = sourceRefFor(value, data, nodes, documentId);
      if (!normalized) return;
      if (!found.some((existing) => JSON.stringify(existing) === JSON.stringify(normalized))) found.push(normalized);
    };
    add(data.source_ref, typeof data.source_doc_node_id === "string" ? data.source_doc_node_id : undefined);
    for (const row of Array.isArray(data.rows) ? data.rows : []) add(record(row).source_ref,
      typeof data.source_doc_node_id === "string" ? data.source_doc_node_id : undefined);
    for (const edge of Object.values(edges)) {
      if (edge.source === nodeId && edge.data?.kind === "evidence") add(edge.data.source_ref, edge.target);
    }
    return found;
  }, [data, nodes, edges, nodeId]);
  if (!node) return null;
  return (
    <aside aria-label="Node details" className="nodrag nopan nowheel absolute bottom-3 right-3 top-3 z-40 flex w-[min(28rem,calc(100%-1.5rem))] flex-col rounded-xl border border-neutral-200 bg-white shadow-xl"
      onPointerDown={(event) => event.stopPropagation()} onDoubleClick={(event) => event.stopPropagation()}>
      <header className="flex items-start justify-between gap-3 border-b px-4 py-3">
        <div><h2 className="text-lg font-semibold">{node.label || "Untitled node"}</h2><p className="text-xs text-neutral-500">{node.node_type}</p></div>
        <button type="button" aria-label="Close node details" onClick={onClose} className="rounded px-2 py-1 text-sm hover:bg-neutral-100">Close</button>
      </header>
      <div className="flex-1 space-y-4 overflow-y-auto p-4 text-sm">
        {typeof data.subtitle === "string" ? <p className="text-neutral-500">{data.subtitle}</p> : null}
        {typeof data.text === "string" ? <div className="whitespace-pre-wrap break-words">
          {node.node_type === "markdown" ? <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents(workspaceSlug)} urlTransform={urlTransform}>{data.text}</ReactMarkdown> : <AnchoredText text={data.text} workspaceSlug={workspaceSlug} />}
        </div> : null}
        {typeof data.description === "string" ? <p className="whitespace-pre-wrap"><AnchoredText text={data.description} workspaceSlug={workspaceSlug} /></p> : null}
        {rows.length ? <section aria-label="Node rows"><h3 className="mb-1 font-semibold">Rows</h3>
          <table className="w-full table-fixed border-collapse"><tbody>{rows.map((row, index) => {
            const ref = sourceRefFor(row.source_ref ?? data.source_ref, data, nodes,
              typeof data.source_doc_node_id === "string" ? data.source_doc_node_id : undefined);
            return <tr key={index} className="border-b align-top">
            <th className="w-2/5 break-words py-2 pr-2 text-left font-medium">{String(row.key ?? "")}</th>
            <td className="break-words py-2">{String(row.value ?? "")}
              <div className="mt-1 flex items-center gap-1 text-[10px] text-neutral-500">
                <span>{evidenceLabels[evidenceState(row)]}</span>
                {ref?.page ? <SourceAnchorButton workspaceSlug={workspaceSlug} refValue={ref}
                  ariaLabel={`Open source for ${String(row.key ?? `row ${index + 1}`)}`} query={String(row.value ?? "")}
                  className="h-5 w-5 border border-sky-200" /> : null}
              </div>
            </td>
          </tr>;
          })}</tbody></table>
        </section> : null}
        {refs.length ? <section aria-label="Node sources"><h3 className="mb-2 font-semibold">Sources</h3>
          {refs.map((ref, index) => <SourceExcerpt key={JSON.stringify(ref)} refValue={ref} workspaceSlug={workspaceSlug} index={index} />)}
        </section> : null}
        {evidence.length ? <section><h3 className="font-semibold">Evidence links</h3><ul className="space-y-1">{evidence.map((edge) => <li key={edge.id}>
          {edge.label || nodes[edge.target]?.label || edge.target}
        </li>)}</ul></section> : null}
        {data.review || data.review_history ? <section><h3 className="font-semibold">Review record</h3>
          <JsonValue value={data.review_history ?? data.review} />
        </section> : null}
        <section aria-label="Node threads"><h3 className="font-semibold">Requests and review history</h3>
          {threadError ? <p role="status" className="text-neutral-500">Could not load node requests.</p> : null}
          {!threads.length && !threadError ? <p className="text-neutral-500">No requests target this node.</p> : null}
          {threads.map((thread) => <article key={thread.id} className="mt-2 rounded border p-2">
            <p className="whitespace-pre-wrap font-medium">{String(thread.payload.text ?? thread.kind)}</p>
            <p className="text-xs text-neutral-500">{thread.status}</p>
            {thread.items?.map((item) => <div key={item.id} className="mt-2 border-t pt-1">
              <p className="text-xs text-neutral-500">{item.author.label ?? item.author.kind}: {item.type}{item.state ? ` (${item.state})` : ""}</p>
              <p className="whitespace-pre-wrap"><AnchoredText text={item.text} workspaceSlug={workspaceSlug} /></p>
              {item.answer ? <p className="whitespace-pre-wrap">Answer: {item.answer}</p> : null}
              <details className="mt-1"><summary className="cursor-pointer text-xs text-neutral-500">Full thread item</summary><JsonValue value={item} /></details>
            </div>)}
          </article>)}
        </section>
        {readOnly ? null : <NodePresentationEditor workspaceSlug={workspaceSlug} node={node} />}
        {readOnly ? null : <button type="button" className="rounded border px-3 py-1 text-xs hover:bg-neutral-50" onClick={() => {
          setSelectedNodeId(nodeId); setPropertiesOpen(true); onClose();
        }}>Edit properties</button>}
        <details><summary className="cursor-pointer text-xs text-neutral-500">All node data</summary><JsonValue value={data} /></details>
      </div>
    </aside>
  );
}

function JsonValue({ value }: { value: unknown }) {
  return <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded bg-neutral-50 p-2 text-xs">{JSON.stringify(value, null, 2)}</pre>;
}

function SourceExcerpt({ refValue, workspaceSlug, index }: { refValue: ResolvableRef; workspaceSlug: string; index: number }) {
  const [place, setPlace] = useState(refValue);
  const [failed, setFailed] = useState(false);
  const open = useOpenSourceRef(workspaceSlug);
  useEffect(() => {
    setPlace(refValue);
    setFailed(false);
    if (!refValue.slug || (!refHasSelector(refValue) && !refValue.region_id)) return;
    let active = true;
    void documents.resolveRef(refValue.slug, refValue).then((resolved) => {
      if (active && resolved) setPlace({ ...refValue, page: resolved.page, bbox: resolved.bbox });
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [refValue]);
  const url = !place.page ? null : place.bbox?.length === 4
    ? documents.pageCropUrl(place.slug!, place.page!, place.bbox)
    : documents.pageImageUrl(place.slug!, place.page!);
  return <div className="mb-3 rounded border p-2">
    <p className="mb-1 text-xs text-neutral-500">{place.slug}{place.page ? `, page ${place.page}` : ", resolving source"}</p>
    {!failed && url ? <img src={url} alt={`Source ${index + 1}: ${place.slug}, page ${place.page}`} loading="lazy" className="mb-2 max-h-64 w-full object-contain" onError={() => setFailed(true)} />
      : <p className="mb-2 text-xs text-neutral-500">Source preview unavailable.</p>}
    <button type="button" disabled={!place.page} className="rounded border border-sky-200 bg-sky-50 px-2 py-1 text-xs text-sky-800 disabled:opacity-50" onClick={() => open(failed ? { slug: place.slug, page: place.page, bbox: place.bbox, also: place.also } : place)}>{place.page ? `Open viewer at page ${place.page}` : "Source page unavailable"}</button>
    <details className="mt-1"><summary className="cursor-pointer text-xs text-neutral-500">Source reference</summary><JsonValue value={refValue} /></details>
  </div>;
}
