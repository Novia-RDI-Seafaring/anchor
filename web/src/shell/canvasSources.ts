import type { ResolvableRef } from "@/api/documents";

type SourceNode = { node_type: string; data?: Record<string, unknown> };
type SourceEdge = { target: string; data?: Record<string, unknown> };

export type CanvasSource = { slug: string; ref?: ResolvableRef };
type SourceContext = { slug?: string; documentNodeId?: unknown; regionId?: unknown };

function record(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function documentSlug(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

/** Only source-bearing fields count; a canvas link or CAD slug is not a PDF. */
export function canvasSources(
  nodes: Record<string, SourceNode>,
  edges: Record<string, SourceEdge>,
): CanvasSource[] {
  const sources = new Map<string, CanvasSource>();
  const cardSlug = (id: unknown) => {
    const node = typeof id === "string" ? nodes[id] : undefined;
    return node?.node_type === "document" ? documentSlug(node.data?.slug) : undefined;
  };
  const addRef = (value: unknown, context: SourceContext = {}) => {
    const ref = record(value);
    if (!ref || (ref.kind != null && ref.kind !== "pdf-page-bbox")) return;
    const fallbackSlug = context.slug ?? cardSlug(ref.doc_id ?? context.documentNodeId);
    const slug = documentSlug(ref.slug) ?? fallbackSlug;
    if (!slug) return;
    const current = sources.get(slug);
    const navigable = typeof ref.page === "number" && Number.isInteger(ref.page) && ref.page > 0;
    const regionId = ref.region_id ?? ref.source_region_id
      ?? (slug === fallbackSlug ? context.regionId : undefined);
    sources.set(slug, {
      slug,
      ref: current?.ref ?? (navigable ? {
        ...ref, slug, ...(regionId ? { region_id: regionId } : {}),
      } as ResolvableRef : undefined),
    });
  };

  for (const node of Object.values(nodes)) {
    const data = node.data ?? {};
    if (node.node_type === "document") {
      const slug = documentSlug(data.slug);
      if (slug && !sources.has(slug)) sources.set(slug, { slug });
    }
    const nodeRef = record(data.source_ref);
    const context = {
      slug: documentSlug(data.source_doc_slug) ?? documentSlug(nodeRef?.slug),
      documentNodeId: data.source_doc_node_id ?? nodeRef?.doc_id,
      regionId: data.source_region_id,
    };
    addRef(data.source_ref, context);
    if (Array.isArray(data.rows)) {
      const rowContext = { ...context, slug: documentSlug(nodeRef?.slug) ?? context.slug };
      for (const value of data.rows) {
        const row = record(value);
        addRef(row?.source_ref, { ...rowContext, regionId: row?.source_region_id ?? rowContext.regionId });
      }
    }
  }

  for (const edge of Object.values(edges)) {
    const data = edge.data ?? {};
    addRef(data.source_ref, {
      slug: documentSlug(data.source_doc_slug),
      documentNodeId: data.source_doc_node_id ?? edge.target,
      regionId: data.source_region_id,
    });
  }

  return [...sources.values()].sort((a, b) => a.slug.localeCompare(b.slug));
}
