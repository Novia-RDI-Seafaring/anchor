/**
 * threadsStore — UI-only state for scoped-ask threads (#344).
 *
 * Which selection the ask composer is open for, which thread the docked
 * panel shows, the fetched thread record, and which suggestion (if any) is
 * ghost-previewed on the canvas. Deliberately separate from the workspace
 * store: nothing here is canvas state, and the ghost preview must never
 * reach into `useCanvasStore` to write.
 */
import { create } from "zustand";

import type { Intent } from "@/api/intents";

type ThreadsState = {
  /** Node ids the ask composer is anchored to; null when closed. */
  composerNodeIds: string[] | null;
  /** The thread the docked panel shows; null when closed. */
  openThreadId: string | null;
  /** The open thread's full record (from `GET /api/intents/{id}`). */
  thread: Intent | null;
  threadError: string | null;
  /** Suggestion item id whose ops are ghost-previewed; null = no preview. */
  previewItemId: string | null;
  /**
   * Bumped by every action result (`applyActionResult`). The sync hook
   * captures it before a GET and drops the response if an action landed
   * meanwhile: a GET served before the POST would otherwise roll the panel
   * back until the next tick.
   */
  actionSeq: number;
  openComposer: (nodeIds: string[]) => void;
  closeComposer: () => void;
  openThread: (id: string) => void;
  closeThread: () => void;
  /** A refetched record (sync). */
  setThread: (thread: Intent) => void;
  /** The record returned by an approve / decline / answer / comment. */
  applyActionResult: (thread: Intent) => void;
  setThreadError: (error: string | null) => void;
  setPreviewItemId: (id: string | null) => void;
  togglePreview: (id: string) => void;
};

/** The record + preview reconciliation shared by both thread setters. */
function withThread(s: ThreadsState, thread: Intent): Partial<ThreadsState> {
  // Clear a preview whose suggestion is no longer pending (applied /
  // declined / superseded elsewhere) — the ghost would lie.
  const previewed = thread.items?.find((i) => i.id === s.previewItemId);
  const keep = previewed && previewed.type === "suggestion" && previewed.state === "pending";
  return { thread, threadError: null, previewItemId: keep ? s.previewItemId : null };
}

export const useThreadsStore = create<ThreadsState>((set) => ({
  composerNodeIds: null,
  openThreadId: null,
  thread: null,
  threadError: null,
  previewItemId: null,
  actionSeq: 0,
  openComposer: (nodeIds) => set({ composerNodeIds: nodeIds.length > 0 ? [...nodeIds] : null }),
  closeComposer: () => set({ composerNodeIds: null }),
  openThread: (id) =>
    set((s) => ({
      openThreadId: id,
      // Keep the record when re-opening the same thread; otherwise start
      // clean so a stale record from another thread never flashes.
      thread: s.thread?.id === id ? s.thread : null,
      threadError: null,
      previewItemId: null,
      composerNodeIds: null,
    })),
  closeThread: () =>
    set({ openThreadId: null, thread: null, threadError: null, previewItemId: null }),
  setThread: (thread) => set((s) => withThread(s, thread)),
  applyActionResult: (thread) =>
    set((s) => ({ ...withThread(s, thread), actionSeq: s.actionSeq + 1 })),
  setThreadError: (error) => set({ threadError: error }),
  setPreviewItemId: (id) => set({ previewItemId: id }),
  togglePreview: (id) => set((s) => ({ previewItemId: s.previewItemId === id ? null : id })),
}));
