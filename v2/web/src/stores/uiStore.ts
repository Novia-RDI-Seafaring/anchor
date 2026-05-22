import { create } from "zustand";

type PdfViewerState = {
  slug: string;             // document slug
  page: number;
  workspaceSlug?: string;   // for "send to canvas" actions
  documentNodeId?: string;  // for evidence-edge wiring
  /** When set, the viewer should focus this region and ride a deep-highlight on its bbox. */
  highlightRegionId?: string;
  highlightBbox?: number[];
};

/**
 * The "live cross-reference" that any canvas element can broadcast on hover.
 * Document nodes that match the slug+page show the region highlighted; spec
 * nodes whose source_ref matches receive a softer reciprocal highlight; edges
 * connecting spec→document pulse on the same signal.
 */
type HoveredSourceRef = {
  slug: string;          // document slug the ref points at
  page: number;
  region_id?: string;    // when known (regions resolved by id)
  bbox?: number[];       // raw bbox in PDF user-space
} | null;

type UiState = {
  pdfViewer: PdfViewerState | null;
  hoveredSourceRef: HoveredSourceRef;
  /**
   * True when the right-side Library drawer (shadcn Sheet) is open.
   * Session-only — the drawer is a transient launcher, not a layout
   * preference, so we don't persist it. Toggled by the Library button on
   * the left tool rail and the `]` keyboard shortcut.
   */
  libraryDrawerOpen: boolean;
  /**
   * draw.io-style "armed tool" state — when set to a node_type string the
   * canvas treats the next click (or click+drag) as a placement gesture
   * for that shape. `null` means no tool is armed and the canvas behaves
   * normally (pan/select).
   *
   * Lifecycle:
   *   - Set by clicking a shape/card icon on the left tool rail.
   *   - Cleared by:
   *       · placing a node on the canvas (click or drag-to-size),
   *       · pressing Escape,
   *       · clicking the same icon a second time (toggle),
   *       · clicking another icon (replaces the value).
   *   - Producer entries (`document`, `cad:model`, ...) do NOT arm; the
   *     `+` menu opens a Dialog instead. Arming is for shapes/cards only.
   */
  armedTool: string | null;
  openPdf: (
    slug: string,
    options?: {
      page?: number;
      workspaceSlug?: string;
      documentNodeId?: string;
      highlightRegionId?: string;
      highlightBbox?: number[];
    },
  ) => void;
  closePdf: () => void;
  setPdfPage: (page: number) => void;
  setHoveredSourceRef: (ref: HoveredSourceRef) => void;
  clearHoveredSourceRef: () => void;
  setLibraryDrawerOpen: (open: boolean) => void;
  toggleLibraryDrawer: () => void;
  /** Arm `type` (or toggle off if already armed for the same type). */
  armTool: (type: string) => void;
  /** Force-disarm whatever tool is currently armed. */
  disarmTool: () => void;
  // --- Properties panel (added by node-content-editing agent) -----------
  /**
   * Id of the currently selected canvas node, or null. Set by ReactFlow's
   * `onNodeClick` handler. The Properties panel reads from this id and
   * pulls the node from `useCanvasStore` so the panel re-renders when
   * the canonical node changes (SSE echoes, label edits, etc.).
   */
  selectedNodeId: string | null;
  /**
   * True when the right-side Properties panel (shadcn Sheet) is open.
   * Mutually exclusive with `libraryDrawerOpen` — opening Properties
   * closes Library, and vice-versa. Documented in PropertiesPanel.tsx.
   */
  propertiesOpen: boolean;
  setSelectedNodeId: (id: string | null) => void;
  setPropertiesOpen: (open: boolean) => void;
  toggleProperties: () => void;
  // --- Drop-target tracking for Area (container) nodes -------------------
  /**
   * Id of the Area node the user is currently hovering a dragged node over,
   * or null when no Area is being targeted.
   *
   * Lives on uiStore (not on the per-node `data` dict on canvasStore) so
   * per-frame mouse updates during a drag don't pollute the canonical
   * canvas state or echo through SSE. Read by `AreaNode` to render the
   * "drop here" highlight; written by `CanvasGraph.onNodeDrag` /
   * `onNodeDragStop`.
   */
  dropTargetAreaId: string | null;
  setDropTargetAreaId: (id: string | null) => void;
};

export const useUiStore = create<UiState>((set) => ({
  pdfViewer: null,
  hoveredSourceRef: null,
  libraryDrawerOpen: false,
  armedTool: null,
  selectedNodeId: null,
  propertiesOpen: false,
  dropTargetAreaId: null,
  openPdf: (slug, options) =>
    set({
      pdfViewer: {
        slug,
        page: options?.page ?? 1,
        workspaceSlug: options?.workspaceSlug,
        documentNodeId: options?.documentNodeId,
        highlightRegionId: options?.highlightRegionId,
        highlightBbox: options?.highlightBbox,
      },
    }),
  closePdf: () => set({ pdfViewer: null }),
  setPdfPage: (page) =>
    set((state) =>
      state.pdfViewer ? { pdfViewer: { ...state.pdfViewer, page } } : state,
    ),
  setHoveredSourceRef: (ref) => set({ hoveredSourceRef: ref }),
  clearHoveredSourceRef: () => set({ hoveredSourceRef: null }),
  setLibraryDrawerOpen: (open) => set({ libraryDrawerOpen: open }),
  toggleLibraryDrawer: () =>
    set((state) => ({ libraryDrawerOpen: !state.libraryDrawerOpen })),
  armTool: (type) =>
    set((state) => ({
      // Clicking the same icon a second time toggles the tool off.
      armedTool: state.armedTool === type ? null : type,
    })),
  disarmTool: () => set({ armedTool: null }),
  // --- Properties panel actions (appended) ------------------------------
  setSelectedNodeId: (id) => set({ selectedNodeId: id }),
  setPropertiesOpen: (open) =>
    set((state) =>
      open
        ? { propertiesOpen: true, libraryDrawerOpen: false }
        : { ...state, propertiesOpen: false },
    ),
  toggleProperties: () =>
    set((state) =>
      state.propertiesOpen
        ? { propertiesOpen: false }
        : { propertiesOpen: true, libraryDrawerOpen: false },
    ),
  setDropTargetAreaId: (id) => set({ dropTargetAreaId: id }),
}));
