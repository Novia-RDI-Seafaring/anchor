import { useEffect, useRef } from "react";

import { pdfjs, type PdfDoc, type PdfViewport } from "./pdfjs";

/**
 * PdfPageCanvas — renders ONE page of the continuous viewer (#220 part A).
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
  /** Notifies the parent of the rendered viewport size (CSS px) once known. */
  onRendered?: (page: number, size: { w: number; h: number }) => void;
};

export function PdfPageCanvas({ doc, page, zoom, onRendered }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const textLayerRef = useRef<HTMLDivElement | null>(null);
  const tokenRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const token = ++tokenRef.current;
    const canvas = canvasRef.current;
    const textLayerDiv = textLayerRef.current;
    if (!canvas || !textLayerDiv) return;

    async function renderPage() {
      if (!canvas || !textLayerDiv) return;
      if (page < 1 || page > doc.numPages) return;
      const pdfPage = await doc.getPage(page);
      if (cancelled || token !== tokenRef.current) return;

      const outputScale = window.devicePixelRatio || 1;
      const viewport: PdfViewport = pdfPage.getViewport({ scale: zoom });
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      canvas.width = Math.floor(viewport.width * outputScale);
      canvas.height = Math.floor(viewport.height * outputScale);
      canvas.style.width = `${Math.floor(viewport.width)}px`;
      canvas.style.height = `${Math.floor(viewport.height)}px`;

      const transform = outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : undefined;
      const renderTask = pdfPage.render({ canvas, canvasContext: ctx, viewport, transform });
      try {
        await renderTask.promise;
      } catch {
        return; // cancelled render
      }
      if (cancelled || token !== tokenRef.current) return;

      textLayerDiv.replaceChildren();
      textLayerDiv.style.width = `${Math.floor(viewport.width)}px`;
      textLayerDiv.style.height = `${Math.floor(viewport.height)}px`;
      textLayerDiv.style.setProperty("--scale-factor", String(zoom));
      textLayerDiv.style.setProperty("--total-scale-factor", String(zoom));
      const textContentSource = pdfPage.streamTextContent();
      const textLayer = new pdfjs.TextLayer({
        textContentSource,
        container: textLayerDiv,
        viewport,
      });
      try {
        await textLayer.render();
      } catch {
        // text layer is best-effort; the canvas raster is the source of truth
      }
      if (cancelled || token !== tokenRef.current) return;
      onRendered?.(page, { w: viewport.width, h: viewport.height });
    }

    void renderPage();
    return () => {
      cancelled = true;
    };
  }, [doc, page, zoom, onRendered]);

  return (
    <>
      <canvas ref={canvasRef} className="block" data-testid="pdf-page-canvas" data-page={page} />
      <div ref={textLayerRef} className="textLayer" style={{ position: "absolute", inset: 0 }} />
    </>
  );
}
