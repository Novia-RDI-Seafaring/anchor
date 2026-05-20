import { api } from "./client";

export type WorkspaceMeta = {
  slug: string;
  title: string;
  created_at: number;
};

export type CanvasState = {
  slug: string;
  title: string;
  version: number;
  nodes: Array<Record<string, unknown> & { id: string }>;
  edges: Array<Record<string, unknown> & { id: string }>;
  metadata: Record<string, unknown>;
};

export const canvases = {
  list: () => api.get<WorkspaceMeta[]>("/api/workspaces"),
  create: (slug: string, title = "") =>
    api.post<WorkspaceMeta>("/api/workspaces", { slug, title }),
  state: (slug: string) => api.get<CanvasState>(`/api/workspaces/${slug}/state`),
  clear: (slug: string) => api.post(`/api/workspaces/${slug}/clear`),
  addNode: (slug: string, body: Record<string, unknown>) =>
    api.post(`/api/workspaces/${slug}/nodes`, body),
  patchNode: (slug: string, id: string, body: Record<string, unknown>) =>
    api.patch(`/api/workspaces/${slug}/nodes/${id}`, body),
  removeNode: (slug: string, id: string) =>
    api.del(`/api/workspaces/${slug}/nodes/${id}`),
  addEdge: (slug: string, body: Record<string, unknown>) =>
    api.post(`/api/workspaces/${slug}/edges`, body),
  removeEdge: (slug: string, id: string) =>
    api.del(`/api/workspaces/${slug}/edges/${id}`),
  organizeSubtree: (
    slug: string,
    rootId: string,
    orientation: "vertical" | "horizontal" = "vertical",
    algo = "dagre",
  ) =>
    api.post<{
      moves: Array<{ id: string; x: number; y: number }>;
      event_count: number;
      state: CanvasState;
    }>(`/api/workspaces/${slug}/layout`, {
      root_id: rootId,
      orientation,
      algo,
    }),
  uploadFile: (slug: string, file: File, x: number, y: number) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("x", String(x));
    fd.append("y", String(y));
    return api.upload<{ slug: string; job_id: string; status: string }>(
      `/api/workspaces/${slug}/upload`,
      fd,
    );
  },
};
