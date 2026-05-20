import { api } from "./client";

export type FmuVariable = {
  name: string;
  causality?: string;
  variability?: string;
  start?: number | string | boolean | null;
  unit?: string | null;
  description?: string;
};

export type FmuModel = {
  slug: string;
  filename: string;
  description?: string;
  variables: FmuVariable[];
};

export const fmu = {
  list: () => api.get<FmuModel[]>("/api/fmu"),
  get: (slug: string) => api.get<FmuModel>(`/api/fmu/${slug}`),
  /**
   * Upload a `.fmu` and have the backend parse its modelDescription.
   * Mirrors `POST /api/fmu` — see anchor_fmus/adapters/http/fmu_routes.py.
   */
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.upload<FmuModel>("/api/fmu", fd);
  },
};
