import { api, BACKEND_URL } from "./client";

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
  /**
   * Align the listed nodes to a shared edge or midline (Miro-style).
   * Backend recomputes the moves, emits one NodeMoved per change with a
   * shared causation_id, and SSE-broadcasts — callers don't need to
   * apply the response moves manually.
   */
  align: (
    slug: string,
    ids: string[],
    anchor: "top" | "bottom" | "left" | "right" | "center-h" | "center-v",
  ) =>
    api.post<{
      moves: Array<{ id: string; x: number; y: number }>;
      event_count: number;
      state: CanvasState;
    }>(`/api/workspaces/${slug}/align`, { ids, anchor }),
  /** Distribute centres evenly along an axis. Endpoints stay. Needs ≥3 ids. */
  distribute: (
    slug: string,
    ids: string[],
    axis: "horizontal" | "vertical",
  ) =>
    api.post<{
      moves: Array<{ id: string; x: number; y: number }>;
      event_count: number;
      state: CanvasState;
    }>(`/api/workspaces/${slug}/distribute`, { ids, axis }),
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
  /**
   * Provision a child workspace and drop a `canvas`-typed linking node
   * onto the parent in one server-side step. Backed by
   * `WorkspaceService.create_sub_canvas` — same code the CLI / MCP call.
   */
  createSubCanvas: (
    parentSlug: string,
    body: { slug: string; title?: string; x?: number; y?: number },
  ) =>
    api.post<{
      child: WorkspaceMeta;
      node: { id: string; node_type: string; label: string; x: number; y: number; data: Record<string, unknown> };
      event: Record<string, unknown>;
      state: CanvasState;
    }>(`/api/workspaces/${parentSlug}/sub-canvas`, body),
  /**
   * URL of the workspace's PNG snapshot endpoint. POST returns image bytes
   * (or a FileResponse when the backend has on-disk caching). The same
   * URL is safe to use as an `<img src>` because fetch fires a POST; for
   * a real `<img>` use the SubCanvasPrimitive's fetch + ObjectURL flow
   * instead.
   */
  snapshotUrl: (slug: string) => `${BACKEND_URL}/api/workspaces/${slug}/snapshot`,
};
