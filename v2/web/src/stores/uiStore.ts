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

// localStorage key for the persisted shell preferences.
const LEFT_RAIL_STORAGE_KEY = "anchor.ui.leftRailCollapsed";

function readLeftRailCollapsed(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(LEFT_RAIL_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeLeftRailCollapsed(value: boolean): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LEFT_RAIL_STORAGE_KEY, value ? "1" : "0");
  } catch {
    /* localStorage unavailable — preference becomes session-local */
  }
}

type UiState = {
  pdfViewer: PdfViewerState | null;
  hoveredSourceRef: HoveredSourceRef;
  /**
   * True when the left rail is in its narrow "icon-only" mode. Persisted
   * across reloads via localStorage. Toggled by the chevron button in the
   * rail header and the `[` keyboard shortcut.
   */
  leftRailCollapsed: boolean;
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
  toggleLeftRail: () => void;
  setLeftRailCollapsed: (collapsed: boolean) => void;
};

export const useUiStore = create<UiState>((set) => ({
  pdfViewer: null,
  hoveredSourceRef: null,
  leftRailCollapsed: readLeftRailCollapsed(),
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
  toggleLeftRail: () =>
    set((state) => {
      const next = !state.leftRailCollapsed;
      writeLeftRailCollapsed(next);
      return { leftRailCollapsed: next };
    }),
  setLeftRailCollapsed: (collapsed) => {
    writeLeftRailCollapsed(collapsed);
    set({ leftRailCollapsed: collapsed });
  },
}));
