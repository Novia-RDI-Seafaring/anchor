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
