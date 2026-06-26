import { create } from "zustand";

type PdfViewerState = {
  slug: string;             // document slug
  page: number;
  workspaceSlug?: string;   // for "send to canvas" actions
  documentNodeId?: string;  // for evidence-edge wiring
  /** When set, the viewer should focus this region and ride a deep-highlight on its bbox. */
  highlightRegionId?: string;
  highlightBbox?: number[];
  highlightPage?: number;
  /**
   * The grounded value's text. When set, the viewer locates this text inside
   * the region (via documents.locate) and draws a value-precise yellow
   * highlight layered over the region rectangle (#197). Falls back to the
   * region-level highlight when the text cannot be located.
   */
  highlightQuery?: string;
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
  /**
   * Marks a deliberate, pinned reference (e.g. broadcast by a *selected*
   * referencing node) as opposed to a transient on-hover signal. A document
   * node treats a transient ref as a temporary page flip that reverts to its
   * resting page on clear, but a sticky ref pins the resting page so the
   * preview stays put after the pointer leaves. Defaults to transient when
   * absent. See DocumentPrimitive's page-flip effect (#187).
   */
  sticky?: boolean;
  /**
   * The grounded value's text. When a spec row broadcasts its hover it carries
   * the cell value here so the document node can draw a value-precise yellow
   * highlight inside the region (#197), not just the region rectangle.
   */
  query?: string;
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
      highlightQuery?: string;
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
  // --- Connector overlay coordination ----------------------------------
  /**
   * True while ReactFlow is actively dragging at least one node. Set by
   * `onNodeDragStart` and cleared by `onNodeDragStop` /
   * `onSelectionDragStop`. Read by `DirectionalConnectors` to hide its
   * 4 N/E/S/W dots — otherwise the dots fight the node-drag gesture and
   * the cursor flicks between move and crosshair.
   */
  isDraggingNode: boolean;
  setIsDraggingNode: (dragging: boolean) => void;
  /**
   * Last node id the pointer entered. Drives the
   * DirectionalConnectors overlay's hover-mode: any hovered node
   * shows quick-add dots even without prior selection. Cleared when
   * the pointer leaves the node OR when the node is selected (the
   * selection path takes priority so a selected node's dots stay put
   * if the user moves the cursor off the node briefly).
   */
  hoveredNodeId: string | null;
  setHoveredNodeId: (id: string | null) => void;
  /**
   * When a node is created via a "quick add" path (DirectionalConnectors
   * click, QuickAddPopover pick), this slot carries the new node's id so
   * the shape primitive's `useInlineField` hook can auto-enter rename
   * mode the moment the node lands. Cleared by `useInlineField` after
   * consumption so the same id doesn't keep re-arming the input.
   *
   * Empty string never matches a real node id — used as a no-op sentinel
   * when chaining clears via setter rather than null because zustand
   * shallow-equality treats null/undefined as identical here.
   */
  pendingInlineRenameNodeId: string | null;
  requestInlineRename: (id: string) => void;
  consumeInlineRename: (id: string) => boolean;
  // --- Edge selection ----------------------------------------------------
  /**
   * Id of the currently selected canvas edge, or null. Mutually exclusive
   * with `selectedNodeId`: setting one clears the other. Drives the
   * Miro-style `EdgeContextToolbar` and the `WaypointEditor` overlay.
   */
  selectedEdgeId: string | null;
  setSelectedEdgeId: (id: string | null) => void;
};

export const useUiStore = create<UiState>((set) => ({
  pdfViewer: null,
  hoveredSourceRef: null,
  libraryDrawerOpen: false,
  armedTool: null,
  selectedNodeId: null,
  propertiesOpen: false,
  dropTargetAreaId: null,
  isDraggingNode: false,
  hoveredNodeId: null,
  pendingInlineRenameNodeId: null,
  selectedEdgeId: null,
  openPdf: (slug, options) =>
    set({
      pdfViewer: {
        slug,
        page: options?.page ?? 1,
        workspaceSlug: options?.workspaceSlug,
        documentNodeId: options?.documentNodeId,
        highlightRegionId: options?.highlightRegionId,
        highlightBbox: options?.highlightBbox,
        highlightQuery: options?.highlightQuery,
        highlightPage: options?.highlightRegionId || options?.highlightBbox
          ? options?.page ?? 1
          : undefined,
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
  // Mutual exclusion with selectedEdgeId — selecting a node deselects any
  // currently-selected edge so the EdgeContextToolbar never shows up at
  // the same time as the NodeContextToolbar. Setting `null` only clears
  // the node selection; edge selection is independently cleared.
  setSelectedNodeId: (id) =>
    set((state) => (id !== null
      ? { selectedNodeId: id, selectedEdgeId: null }
      : { ...state, selectedNodeId: null })),
  setSelectedEdgeId: (id) =>
    set((state) => (id !== null
      ? { selectedEdgeId: id, selectedNodeId: null }
      : { ...state, selectedEdgeId: null })),
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
  setIsDraggingNode: (dragging) => set({ isDraggingNode: dragging }),
  setHoveredNodeId: (id) => set({ hoveredNodeId: id }),
  requestInlineRename: (id) => set({ pendingInlineRenameNodeId: id }),
  // Consume returns true iff the requested id matches the pending one;
  // either way the slot is cleared so a re-render doesn't keep re-firing
  // the rename. Tests can stub this out via `useUiStore.setState`.
  consumeInlineRename: (id) => {
    const pending = useUiStore.getState().pendingInlineRenameNodeId;
    if (pending && pending === id) {
      useUiStore.setState({ pendingInlineRenameNodeId: null });
      return true;
    }
    return false;
  },
}));
