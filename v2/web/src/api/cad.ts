import { api, BACKEND_URL } from "./client";

export type CadParameter = {
  name: string;
  value: number | string | boolean;
  unit?: string | null;
  description?: string;
  minimum?: number | null;
  maximum?: number | null;
  default?: number | string | boolean | null;
};

export type CadGeometryStats = {
  triangle_count?: number | null;
  vertex_count?: number | null;
  bounding_box?: number[] | null;
  units?: string | null;
};

export type CadModel = {
  slug: string;
  filename: string;
  kind: string;
  title?: string;
  description?: string;
  parameters: CadParameter[];
  parts: Array<{ id: string; name?: string; kind?: string; parent_id?: string | null }>;
  geometry: CadGeometryStats;
};

export const cad = {
  list: () => api.get<CadModel[]>("/api/cad"),
  get: (slug: string) => api.get<CadModel>(`/api/cad/${slug}`),
  modelUrl: (slug: string) => `${BACKEND_URL}/api/cad/${slug}/model`,
};
