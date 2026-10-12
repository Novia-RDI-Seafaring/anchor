import type { RowBand, Cut } from "./cuts";
import type { Box, Point } from "./lasso";
import type { Sketch } from "./sketch";
import type { Strike, EdgePath } from "./strikes";
import type { Pointer } from "./pointers";

export type Place = { x: number; y: number; width?: number; height?: number };
export type ThreadItem = {
  id: string;
  type: "message" | "question" | "suggestion" | "result";
  author: { kind: string; label?: string | null; id?: string | null };
  text: string;
  created_at: number;
  state: string | null;
  answer?: string;
  ops?: Record<string, unknown>[];
  supersedes?: string;
  applied_versions?: number[];
  place?: Place;
  options?: string[];
};

/** Transport metadata is preserved, but target identity is host-owned. */
export type Intent = {
  id: string;
  payload: Record<string, unknown>;
  status: string;
  created_at: number;
  resolved_at?: number;
  result?: Record<string, unknown>;
  targetIds?: string[];
  items?: ThreadItem[];
};
export type Submission = {
  text: string;
  targetIds: string[];
  sketch?: Sketch;
  cuts?: Cut[];
  strikes?: Strike[];
  pointers?: Pointer[];
};

/** Apply/revert call the host; the renderer never executes ops. */
export type ThreadPort = {
  loadScoped(): Promise<Intent[]>;
  get(id: string): Promise<Intent | null>;
  submit(remark: Submission): Promise<Intent>;
  addItem(id: string, body: { type: ThreadItem["type"]; text?: string; place?: Place; options?: string[] }): Promise<ThreadItem>;
  answer(id: string, itemId: string, text: string): Promise<ThreadItem>;
  apply(id: string, itemId: string): Promise<ThreadItem>;
  revert(id: string, itemId: string): Promise<ThreadItem>;
  decline(id: string, itemId: string, comment?: string): Promise<ThreadItem>;
  resolve(id: string, result?: Record<string, unknown>): Promise<unknown>;
  subscribeChanged(onChanged: () => void): () => void;
};
export type PreviewRow = { key: string; value: string };
export type PreviewNode = Box & {
  kind: "added" | "updated" | "removed";
  label: string;
  rows: PreviewRow[];
  before?: { label: string; rows: PreviewRow[] };
};
/** Endpoints are resolved by the host, including endpoints of new elements. */
export type PreviewEdge = {
  id: string;
  kind: "added" | "removed";
  from: Point | null;
  to: Point | null;
};
export type Preview = { nodes: PreviewNode[]; edges: PreviewEdge[] };
export type Viewport = { x: number; y: number; zoom: number };
export type OverlayHost = {
  geometry: {
    boxes: Box[];
    viewport: Viewport;
    screenToWorld(point: Point): Point;
    getViewport(): Viewport;
    setViewport(viewport: Viewport, options?: { duration?: number }): unknown;
    rowsOf(targetId: string): RowBand[] | null;
    edgesOf(): EdgePath[];
  };
  display: {
    labelOf(targetId: string): string;
    preview(item: ThreadItem): Preview | null;
  };
  thread: ThreadPort;
  input?: {
    /** True assigns a lifted press to host panning rather than a link/field. */
    capturesLiftedPress?(target: EventTarget | null): boolean;
    onLiftedChange?(lifted: boolean): void;
    onPanningChange?(panning: boolean): void;
  };
};
