import { api, BACKEND_URL } from "./client";

export type DocumentSummary = {
  slug: string;
  title: string;
  filename: string;
  page_count: number;
  has_gold: boolean;
  region_count: number;
};

export type DocumentIndex = {
  document: { filename: string; title: string; page_count: number };
  outline: Array<{ level: number; title: string; page: number; bbox: number[] }>;
  tables?: Array<Record<string, unknown>>;
  figures?: Array<Record<string, unknown>>;
};

export type Region = {
  id?: string;
  kind?: string;
  title?: string;
  description?: string;
  page?: number;
  bbox?: number[];
  approximate_bbox?: number[];
  crops?: { png?: string | null; svg?: string | null; pdf?: string | null };
  [key: string]: unknown;
};

type RegionsResponse = { slug: string; pages: Record<string, Region[]> };

/**
 * A source_ref loose enough to cover node / row / edge refs. The optional
 * selectors point below the region (#242 P2): `item_id` names one silver
 * item (`p<page>-i<n>`), `cell` a `{row, col}` of a table.
 */
export type ResolvableRef = {
  slug?: string;
  page?: number;
  bbox?: number[];
  region_id?: string;
  item_id?: string;
  cell?: { row?: number; col?: number } | null;
};

/** Answer of `GET /api/documents/{slug}/resolve-ref` (#242 P2b). */
export type ResolvedRef = {
  slug: string;
  page: number;
  bbox: number[];
  /** Which layer resolved: cell > item > region > bbox. */
  precision: "cell" | "item" | "region" | "bbox";
  region_id?: string;
  item_id?: string;
  cell?: { row: number; col: number };
};

/**
 * True when `ref` carries a below-region selector (`cell` or `item_id`)
 * the backend resolver can turn into a tighter stored bbox (#242 P2c).
 * Refs without a selector take the unchanged region-level highlight path —
 * no request is made for them.
 */
export function refHasSelector(ref: ResolvableRef | null | undefined): boolean {
  if (!ref) return false;
  if (typeof ref.item_id === "string" && ref.item_id.length > 0) return true;
  return typeof ref.cell?.row === "number" && typeof ref.cell?.col === "number";
}

function normaliseRegion(region: Region): Region {
  if (region.bbox || !region.approximate_bbox) return region;
  return { ...region, bbox: region.approximate_bbox };
}

export const documents = {
  list: () => api.get<DocumentSummary[]>("/api/documents"),
  index: (slug: string) => api.get<DocumentIndex>(`/api/documents/${slug}/index`),
  regions: async (slug: string, page?: number): Promise<Region[]> => {
    const q = page !== undefined ? `?page=${page}` : "";
    const rsp = await api.get<RegionsResponse>(`/api/documents/${slug}/regions${q}`);
    if (page !== undefined) return (rsp.pages?.[String(page)] ?? []).map(normaliseRegion);
    // No page filter: flatten all pages.
    return Object.values(rsp.pages ?? {}).flat().map(normaliseRegion);
  },
  goldMap: (slug: string) => api.get<Record<string, unknown>>(`/api/documents/${slug}/gold-map`),
  /**
   * Resolve a source_ref to the most precise stored evidence bbox via
   * `GET /api/documents/{slug}/resolve-ref` (#242 P2b/P2c). Precedence
   * (cell > item > region) is decided server-side, so the viewer never
   * re-implements it. Resolves to `null` (never throws) on 404/error so
   * the caller falls back to the ref's own bbox — the pre-#274 highlight.
   */
  resolveRef: async (slug: string, ref: ResolvableRef): Promise<ResolvedRef | null> => {
    const params = new URLSearchParams();
    if (typeof ref.page === "number") params.set("page", String(ref.page));
    if (ref.region_id) params.set("region_id", ref.region_id);
    if (ref.item_id) params.set("item_id", ref.item_id);
    if (typeof ref.cell?.row === "number" && typeof ref.cell?.col === "number") {
      params.set("row", String(ref.cell.row));
      params.set("col", String(ref.cell.col));
    }
    try {
      const rsp = await api.get<ResolvedRef>(
        `/api/documents/${slug}/resolve-ref?${params.toString()}`,
      );
      if (typeof rsp?.page === "number" && Array.isArray(rsp.bbox) && rsp.bbox.length === 4) {
        return rsp;
      }
      return null;
    } catch {
      return null;
    }
  },
  /**
   * Locate `query` on a page and return its page-space quad(s) (value-precise
   * highlight, #197). `bbox` clips the search to a region so a value that
   * repeats elsewhere on the page resolves to the right spot. Quads come back
   * in the same coordinate convention region bboxes use, so they ride through
   * `bboxToImageRect` unchanged. Resolves to `[]` (never throws) when the text
   * cannot be located so the caller falls back to the region-level highlight.
   */
  locate: async (
    slug: string,
    page: number,
    query: string,
    bbox?: number[],
  ): Promise<number[][]> => {
    const params = new URLSearchParams({ query });
    if (bbox && bbox.length === 4) params.set("bbox", bbox.join(","));
    try {
      const rsp = await api.get<{ quads?: number[][] }>(
        `/api/documents/${slug}/pages/${page}/locate?${params.toString()}`,
      );
      return Array.isArray(rsp.quads) ? rsp.quads : [];
    } catch {
      return [];
    }
  },
  pageText: (slug: string, page: number) =>
    api.get<{ text: string }>(`/api/documents/${slug}/pages/${page}/text`),
  /**
   * URL of the original PDF file. Used by the real-PDF source viewer
   * (PDF.js) so the user gets a selectable text layer instead of a page
   * screenshot. Served by `GET /api/documents/{slug}/pdf`.
   */
  pdfUrl: (slug: string) => `${BACKEND_URL}/api/documents/${slug}/pdf`,
  pageImageUrl: (slug: string, page: number) =>
    `${BACKEND_URL}/api/documents/${slug}/pages/${page}/image`,
  pageCropUrl: (slug: string, page: number, bbox: number[], dpi = 300) =>
    `${BACKEND_URL}/api/documents/${slug}/pages/${page}/crop?${new URLSearchParams({
      bbox: bbox.join(","),
      dpi: String(dpi),
    }).toString()}`,
  cropUrl: (slug: string, relPath: string) =>
    `${BACKEND_URL}/api/documents/${slug}/crops/${relPath}`,
};
