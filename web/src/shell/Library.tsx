/**
 * Library — browse OIP-ingested artefacts (documents, CAD models, ...) and
 * drop them onto the canvas as nodes.
 *
 * Hits `/api/documents` and `/api/cad` directly. Any future producer that
 * exposes a list endpoint plugs in here — the library is a federation of
 * per-producer browsers, not Anchor-specific.
 */
import { useEffect, useState } from "react";

import { cad, type CadModel } from "@/api/cad";
import { documents, type DocumentSummary } from "@/api/documents";

type Props = { workspaceSlug: string };

export function Library({ workspaceSlug: _workspaceSlug }: Props) {
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [cads, setCads] = useState<CadModel[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      try {
        const [d, c] = await Promise.all([
          documents.list().catch(() => [] as DocumentSummary[]),
          cad.list().catch(() => [] as CadModel[]),
        ]);
        if (!cancelled) {
          setDocs(d);
          setCads(c);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    };

    refresh();
    // Light polling — every 8s. SSE for documents/cad lists isn't wired yet.
    const id = window.setInterval(refresh, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <div className="space-y-3">
      <Section title={`Documents (${docs.length})`} subtitle="anchor_pdfs">
        {docs.length === 0 ? (
          <Empty hint="ingest a PDF — drop it on the canvas or use anchor ingest" />
        ) : (
          docs.map((d) => (
            <DraggableItem
              key={d.slug}
              label={d.title || d.slug}
              hint={`${d.page_count}p${d.has_gold ? " · gold" : ""}`}
              payload={{
                node_type: "document",
                label: d.title || d.filename,
                data: {
                  slug: d.slug,
                  filename: d.filename,
                  page_count: d.page_count,
                  region_count: d.region_count,
                  status: "ready",
                },
              }}
            />
          ))
        )}
      </Section>

      <Section title={`CAD models (${cads.length})`} subtitle="anchor_cad">
        {cads.length === 0 ? (
          <Empty hint="no CAD models yet — use cad.inspect via MCP" />
        ) : (
          cads.map((c) => (
            <DraggableItem
              key={c.slug}
              label={c.title || c.filename || c.slug}
              hint={`${c.kind}${c.geometry?.triangle_count ? ` · ${c.geometry.triangle_count} tris` : ""}`}
              payload={{
                node_type: "cad:model",
                label: c.title || c.filename || c.slug,
                data: {
                  cad_slug: c.slug,
                  kind: c.kind,
                  parameters: c.parameters?.map((p) => p.name) ?? [],
                },
              }}
            />
          ))
        )}
      </Section>

      {error ? (
        <div className="px-2 text-[10px] text-red-600">error: {error}</div>
      ) : null}
    </div>
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between px-2 pt-1 pb-1">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
          {title}
        </div>
        {subtitle ? (
          <div className="text-[9px] italic text-neutral-400">{subtitle}</div>
        ) : null}
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function Empty({ hint }: { hint: string }) {
  return (
    <div className="rounded border border-dashed border-neutral-300 px-2 py-2 text-[10px] italic text-neutral-500">
      {hint}
    </div>
  );
}

function DraggableItem({
  label,
  hint,
  payload,
}: {
  label: string;
  hint: string;
  payload: { node_type: string; label?: string; data?: Record<string, unknown> };
}) {
  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "copy";
        e.dataTransfer.setData("application/x-anchor-node", JSON.stringify(payload));
      }}
      className="cursor-grab rounded border border-neutral-200 bg-white px-2 py-1.5 text-xs hover:bg-neutral-50 active:cursor-grabbing"
      title={hint}
    >
      <div className="truncate font-medium text-neutral-800">{label}</div>
      <div className="text-[10px] italic text-neutral-500">{hint}</div>
    </div>
  );
}
