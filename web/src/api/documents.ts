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
  pageText: (slug: string, page: number) =>
    api.get<{ text: string }>(`/api/documents/${slug}/pages/${page}/text`),
  pageImageUrl: (slug: string, page: number) =>
    `${BACKEND_URL}/api/documents/${slug}/pages/${page}/image`,
};
