import { create } from "zustand";

type PdfViewerState = {
  slug: string;             // document slug
  page: number;
  workspaceSlug?: string;   // for "send to canvas" actions
  documentNodeId?: string;  // for evidence-edge wiring
};

type UiState = {
  pdfViewer: PdfViewerState | null;
  openPdf: (
    slug: string,
    options?: { page?: number; workspaceSlug?: string; documentNodeId?: string },
  ) => void;
  closePdf: () => void;
  setPdfPage: (page: number) => void;
};

export const useUiStore = create<UiState>((set) => ({
  pdfViewer: null,
  openPdf: (slug, options) =>
    set({
      pdfViewer: {
        slug,
        page: options?.page ?? 1,
        workspaceSlug: options?.workspaceSlug,
        documentNodeId: options?.documentNodeId,
      },
    }),
  closePdf: () => set({ pdfViewer: null }),
  setPdfPage: (page) =>
    set((state) =>
      state.pdfViewer ? { pdfViewer: { ...state.pdfViewer, page } } : state,
    ),
}));
