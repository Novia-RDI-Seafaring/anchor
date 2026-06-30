/**
 * Thin wrapper around pdfjs-dist that pins the worker once and exposes a
 * small surface to the source viewer. Keeping pdfjs imports behind this
 * module means tests (and any non-PDF code) never pull the worker in.
 *
 * PDF.js 6.x ships ES-module builds. Vite resolves `?url` to the bundled
 * worker asset so it loads from our own origin (no CDN), which keeps the
 * viewer working offline / behind the `anchor serve` proxy.
 */
import * as pdfjs from "pdfjs-dist";
// Vite resolves `?url` to the bundled worker asset (served from our origin).
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

let configured = false;

function ensureWorker(): void {
  if (configured) return;
  pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
  configured = true;
}

export type PdfDoc = pdfjs.PDFDocumentProxy;
export type PdfPage = pdfjs.PDFPageProxy;
export type PdfViewport = pdfjs.PageViewport;

export type LoadedPdf = {
  doc: PdfDoc;
  /** Abort network + tear down the worker for this document. */
  destroy: () => Promise<void>;
};

/** Load a PDF document from a URL. */
export async function loadPdf(url: string): Promise<LoadedPdf> {
  ensureWorker();
  const task = pdfjs.getDocument({ url });
  const doc = await task.promise;
  return { doc, destroy: () => task.destroy() };
}

export { pdfjs };
