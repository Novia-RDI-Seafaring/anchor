/**
 * Thin wrapper around pdfjs-dist that pins the worker once and exposes a
 * small surface to the source viewer. Keeping pdfjs imports behind this
 * module means tests (and any non-PDF code) never pull the worker in.
 *
 * PDF.js 6.x ships ES-module builds. Vite resolves `?url` to the bundled
 * worker asset so it loads from our own origin (no CDN), which keeps the
 * viewer working offline / behind the `anchor serve` proxy.
 */
import type * as pdfjs from "pdfjs-dist";
// Vite resolves `?url` to the bundled worker asset (served from our origin).
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

let configured = false;
let library: Promise<typeof import("pdfjs-dist")> | null = null;

/** Module initialization failures belong to the viewer's load-error path. */
export function getPdfLibrary(): Promise<typeof import("pdfjs-dist")> {
  return library ??= import("pdfjs-dist");
}

function ensureWorker(api: typeof import("pdfjs-dist")): void {
  if (configured) return;
  api.GlobalWorkerOptions.workerSrc = workerUrl;
  configured = true;
}

export type PdfDoc = pdfjs.PDFDocumentProxy;
export type PdfPage = pdfjs.PDFPageProxy;
export type PdfViewport = pdfjs.PageViewport;
export type PdfTextLayer = pdfjs.TextLayer;

export type LoadedPdf = {
  doc: PdfDoc;
  /** Abort network + tear down the worker for this document. */
  destroy: () => Promise<void>;
};

/** Load a PDF document from a URL. */
export async function loadPdf(url: string): Promise<LoadedPdf> {
  const api = await getPdfLibrary();
  ensureWorker(api);
  const task = api.getDocument({ url });
  try {
    const doc = await task.promise;
    return { doc, destroy: () => task.destroy() };
  } catch (error) {
    await task.destroy().catch(() => {});
    throw error;
  }
}

/**
 * Page sizes in PDF points (unscaled), keyed by 1-based page number. The
 * continuous viewer (#220) uses these to lay every page out at the right height
 * before any canvas renders, so the scroll height and scroll-to-page math are
 * correct from the start. Cheap: `getPage` only parses the page dict, not its
 * content stream.
 */
export async function pageSizes(
  doc: PdfDoc,
): Promise<Record<number, { w: number; h: number }>> {
  const out: Record<number, { w: number; h: number }> = {};
  for (let page = 1; page <= doc.numPages; page++) {
    const pdfPage = await doc.getPage(page);
    const [x0, y0, x1, y1] = pdfPage.view; // [x0, y0, x1, y1] in points
    out[page] = { w: (x1 ?? 0) - (x0 ?? 0), h: (y1 ?? 0) - (y0 ?? 0) };
  }
  return out;
}
