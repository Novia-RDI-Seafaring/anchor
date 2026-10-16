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
  /** Who applied a suggestion: a person approving it, or its agent acting. */
  applied_by?: { kind: string; label?: string | null; id?: string | null } | null;
  /** Applied suggestion only: the ops that put the canvas back. */
  undo_ops?: Record<string, unknown>[];
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
  /** When an agent's inbox read first returned it, in epoch seconds. */
  seen_at?: number;
  /** Who read it: `{kind: "agent", label: "claude-code"}`. */
  seen_by?: { kind: string; label?: string | null } | null;
};
export type Submission = {
  text: string;
  targetIds: string[];
  sketch?: Sketch;
  cuts?: Cut[];
  strikes?: Strike[];
  pointers?: Pointer[];
  /** Where the remark was written, so "here" means somewhere. */
  at?: Point;
  /** The view when it was sent: the reply brings the reader back to it. */
  viewport?: Viewport;
  /** The ink as drawn, so a reload redraws the remark rather than its reading. */
  ink?: Ink;
};
/** Strokes and their words as drawn; notes keep their own fields. */
export type Ink = { marks: { points: Point[]; color: string }[]; notes: Record<string, unknown>[] };

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
export type Preview = {
  nodes: PreviewNode[];
  edges: PreviewEdge[];
  /** The host skipped an operation because its target no longer exists. */
  stale?: boolean;
};
/**
 * A real element an applied change touched, while the reader has not ruled
 * on it. `was` is the label it had before a rename.
 */
export type ChangeMark = { id: string; element: "node" | "edge"; kind: "added" | "updated"; was?: string };
/** What an applied change did: the elements it touched, and what it took away. */
export type Changes = { marks: ChangeMark[]; removed: Preview };
/** A mark as the host should draw it: in the remark's colour, stronger on hover. */
export type ShownMark = ChangeMark & { color: string; strong: boolean };
export type Viewport = { x: number; y: number; zoom: number };
export type OverlayHost = {
  geometry: {
    boxes: Box[];
    viewport: Viewport;
    screenToWorld(point: Point): Point;
    getViewport(): Viewport;
    setViewport(viewport: Viewport, options?: { duration?: number }): unknown;
    /** The size of the visible canvas in screen pixels. */
    paneSize?(): { width: number; height: number } | null;
    /** Bring a world rectangle into view. */
    fitBounds?(rect: { x: number; y: number; width: number; height: number }, options?: { padding?: number; duration?: number }): unknown;
    rowsOf(targetId: string): RowBand[] | null;
    edgesOf(): EdgePath[];
  };
  display: {
    labelOf(targetId: string): string;
    preview(item: ThreadItem): Preview | null;
    /** What an applied suggestion changed, read from its undo ops. */
    changes?(item: ThreadItem): Changes | null;
    /** Mark the real elements an applied change touched; [] clears them. */
    markChanges?(marks: ShownMark[]): void;
    /**
     * What to tell the asker when no agent has read a remark: a prompt to
     * paste into their agent, and a shell command that reads the inbox.
     */
    listenHint?: { prompt: string; command?: string };
  };
  thread: ThreadPort;
  input?: {
    /** True assigns a lifted press to host panning rather than a link/field. */
    capturesLiftedPress?(target: EventTarget | null): boolean;
    onLiftedChange?(lifted: boolean): void;
    onPanningChange?(panning: boolean): void;
  };
};
