import { useEffect, useRef, useState } from "react";

import { getPdfLibrary, type PdfDoc, type PdfTextLayer, type PdfViewport } from "./pdfjs";
import { registerTextLayerSelection } from "./textLayerSelection";

/**
 * PdfPageCanvas renders one page of the continuous viewer (#220 part A).
 *
 * Mounted only for pages near the viewport (the virtualization window in
 * PdfSourceView); off-screen pages stay sized placeholders. Draws the PDF.js
 * canvas raster for crisp glyphs plus an absolutely-positioned text layer so
 * selection / copy / browser-find keep working per page. Reports the rendered
 * viewport size back so the parent can map bboxes -> pixels for the overlays.
 */

type Props = {
  doc: PdfDoc;
  page: number;
  zoom: number;
  /** The raster is on screen; `size` is its CSS size and `zoom` what it was drawn at. */
  onRendered?: (page: number, size: { w: number; h: number; zoom: number }) => void;
};

export function PdfPageCanvas({ doc, page, zoom, onRendered }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const textLayerRef = useRef<HTMLDivElement | null>(null);
  const disposeSelectionRef = useRef<(() => void) | null>(null);
  const pendingRef = useRef<Promise<void>>(Promise.resolve());
  const [renderError, setRenderError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    // Cancellation can settle asynchronously. Wait for the previous attempt
    // before starting replacement work, including its text layer.
    const previous = pendingRef.current;
    let renderTask: { cancel: () => void; promise: Promise<unknown> } | null = null;
    let textLayer: PdfTextLayer | null = null;
    const canvas = canvasRef.current;
    const textLayerDiv = textLayerRef.current;
    if (!canvas || !textLayerDiv) return;
    setRenderError(false);

    async function renderPage() {
      try {
        await previous;
        if (cancelled || !canvas || !textLayerDiv) return;
        if (page < 1 || page > doc.numPages) throw new Error("PDF page is out of range");
        const pdfPage = await doc.getPage(page);
        if (cancelled) return;

        const outputScale = window.devicePixelRatio || 1;
        const viewport: PdfViewport = pdfPage.getViewport({ scale: zoom });
        // Resizing the visible canvas clears it. Keep its last good raster and
        // matching text until a replacement is ready to commit together.
        const stagingCanvas = document.createElement("canvas");
        stagingCanvas.width = Math.floor(viewport.width * outputScale);
        stagingCanvas.height = Math.floor(viewport.height * outputScale);
        const ctx = stagingCanvas.getContext("2d");
        const visibleCtx = canvas.getContext("2d");
        if (!ctx || !visibleCtx) throw new Error("Canvas rendering is unavailable");

        const transform = outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : undefined;
        renderTask = pdfPage.render({ canvas: stagingCanvas, canvasContext: ctx, viewport, transform });
        await renderTask.promise;
        renderTask = null;
        if (cancelled) return;

        const stagingText = document.createElement("div");
        stagingText.className = "textLayer";
        stagingText.style.width = `${viewport.width}px`;
        stagingText.style.height = `${viewport.height}px`;
        stagingText.style.setProperty("--scale-factor", String(zoom));
        stagingText.style.setProperty("--total-scale-factor", String(zoom));
        try {
          const { TextLayer } = await getPdfLibrary();
          if (cancelled) return;
          textLayer = new TextLayer({
            textContentSource: pdfPage.streamTextContent(),
            container: stagingText,
            viewport,
          });
          await textLayer.render();
        } catch (error) {
          if (!cancelled && !isRenderCancellation(error)) {
            console.warn(`Could not render PDF text on page ${page}`, error);
          }
          stagingText.replaceChildren();
        }
        if (cancelled) return;

        canvas.width = stagingCanvas.width;
        canvas.height = stagingCanvas.height;
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        visibleCtx.drawImage(stagingCanvas, 0, 0);
        disposeSelectionRef.current?.();
        textLayerDiv.style.cssText = stagingText.style.cssText;
        textLayerDiv.style.position = "absolute";
        textLayerDiv.style.inset = "0";
        textLayerDiv.setAttribute("data-main-rotation", String(viewport.rotation));
        textLayerDiv.replaceChildren(...stagingText.childNodes);
        // Constrain selection to this page (multi-column gap handling).
        disposeSelectionRef.current = registerTextLayerSelection(textLayerDiv);
        onRendered?.(page, { w: viewport.width, h: viewport.height, zoom });
      } catch (error) {
        if (!cancelled && !isRenderCancellation(error)) {
          console.error(`Could not render PDF page ${page}`, error);
          setRenderError(true);
        }
      } finally {
        renderTask = null;
      }
    }

    pendingRef.current = renderPage();
    return () => {
      cancelled = true;
      renderTask?.cancel();
      textLayer?.cancel();
    };
  }, [doc, page, zoom, onRendered, attempt]);

  useEffect(() => () => disposeSelectionRef.current?.(), []);

  return (
    <>
      <canvas ref={canvasRef} className="block" data-testid="pdf-page-canvas" data-page={page} />
      <div ref={textLayerRef} className="textLayer" style={{ position: "absolute", inset: 0 }} />
      {renderError ? (
        <div role="alert" className="absolute left-2 top-2 z-20 rounded border border-red-200 bg-white p-3 text-sm text-red-700 shadow">
          <p>Page {page} could not be rendered. Retry this page or reload the viewer.</p>
          <button type="button" className="mt-2 rounded border border-red-300 px-2 py-1" onClick={() => setAttempt((value) => value + 1)}>
            Retry page
          </button>
        </div>
      ) : null}
    </>
  );
}

function isRenderCancellation(error: unknown): boolean {
  return typeof error === "object" && error !== null && "name" in error
    && error.name === "RenderingCancelledException";
}
