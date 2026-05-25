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
  /**
   * Upload a CAD file (STL/STEP/OBJ/glTF/...) and have the backend parse
   * its parameter and parts summary. Mirrors `POST /api/cad` — see
   * anchor_cad/adapters/http/cad_routes.py.
   */
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.upload<CadModel>("/api/cad", fd);
  },
};
