import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";

import { bboxToViewportRect, type PixelRect } from "@/lib/pdfHighlight";

import type { PdfDoc } from "./pdfjs";
import { intersectRects, MAGNIFIER_SCALE, placeMagnifier } from "./sourceMagnifierGeometry";

type Props = {
  doc: PdfDoc;
  page: number;
  bbox: number[];
  zoom: number;
  pageSize: { w: number; h: number };
  pageRect: PixelRect;
  sourceRect: PixelRect;
  contentRef: RefObject<HTMLDivElement | null>;
  scrollRef: RefObject<HTMLDivElement | null>;
};

/** One bounded, separately rasterized crop. It never intercepts PDF selection. */
export function SourceMagnifier({
  doc, page, bbox, zoom, pageSize, pageRect, sourceRect, contentRef, scrollRef,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const previousRender = useRef<Promise<void>>(Promise.resolve());
  const [placement, setPlacement] = useState<PixelRect | null>(null);
  const [result, setResult] = useState<{ doc: PdfDoc; key: string; status: "ready" | "error" } | null>(null);
  const [x0, y0, x1, y1] = bbox;

  useLayoutEffect(() => {
    const scroller = scrollRef.current;
    const content = contentRef.current;
    if (!scroller || !content) return;
    const update = () => {
      const visible = {
        left: scroller.scrollLeft - content.offsetLeft,
        top: scroller.scrollTop - content.offsetTop,
        width: scroller.clientWidth, height: scroller.clientHeight,
      };
      const visibleSource = intersectRects(sourceRect, visible);
      // Prefer the source page; the viewport gutter can fit a broad region.
      const next = visibleSource.width > 0 && visibleSource.height > 0
        ? placeMagnifier(sourceRect, intersectRects(pageRect, visible))
          ?? placeMagnifier(sourceRect, visible)
        : null;
      if (!next) setResult(null);
      setPlacement((old) => old?.left === next?.left && old?.top === next?.top
        && old?.width === next?.width && old?.height === next?.height ? old : next);
    };
    update();
    scroller.addEventListener("scroll", update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(scroller);
    return () => { scroller.removeEventListener("scroll", update); observer.disconnect(); };
  }, [contentRef, scrollRef, pageRect.left, pageRect.top, pageRect.width, pageRect.height,
    sourceRect.left, sourceRect.top, sourceRect.width, sourceRect.height]);

  const width = placement?.width ?? 0;
  const height = placement?.height ?? 0;
  const renderKey = `${page}:${x0}:${y0}:${x1}:${y1}:${zoom}:${pageSize.w}:${pageSize.h}:${width}:${height}`;
  const status = result?.doc === doc && result.key === renderKey ? result.status : "loading";
  useEffect(() => {
    if (!width || !height || page < 1 || page > doc.numPages
      || ![x0, y0, x1, y1, zoom, pageSize.w, pageSize.h].every((n) => Number.isFinite(n))
      || zoom <= 0 || pageSize.w <= 0 || pageSize.h <= 0) return;
    let cancelled = false;
    let task: { cancel: () => void; promise: Promise<unknown> } | null = null;
    const previous = previousRender.current;
    const timer = window.setTimeout(() => {
      const render = async () => {
        await previous;
        if (cancelled) return;
        const staging = document.createElement("canvas");
        try {
          const pdfPage = await doc.getPage(page);
          if (cancelled) return;
          const viewport = pdfPage.getViewport({ scale: zoom * MAGNIFIER_SCALE });
          const rect = bboxToViewportRect([x0!, y0!, x1!, y1!], pageSize.w, pageSize.h, viewport);
          if (!rect || rect.width <= 0 || rect.height <= 0) throw new Error("Source box is unavailable");
          const dpr = Math.min(3, Math.max(1, window.devicePixelRatio || 1));
          staging.width = Math.ceil(width * dpr);
          staging.height = Math.ceil(height * dpr);
          task = pdfPage.render({
            canvas: staging, viewport,
            transform: [dpr, 0, 0, dpr,
              staging.width / 2 - (rect.left + rect.width / 2) * dpr,
              staging.height / 2 - (rect.top + rect.height / 2) * dpr],
            background: "rgb(255,255,255)",
          });
          await task.promise;
          if (cancelled) return;
          const canvas = canvasRef.current;
          const ctx = canvas?.getContext("2d");
          if (!canvas || !ctx) throw new Error("Canvas is unavailable");
          canvas.width = staging.width;
          canvas.height = staging.height;
          ctx.drawImage(staging, 0, 0);
          setResult({ doc, key: renderKey, status: "ready" });
        } catch {
          if (!cancelled) setResult({ doc, key: renderKey, status: "error" });
        } finally {
          task = null;
          staging.width = staging.height = 0;
        }
      };
      previousRender.current = render();
    }, 120);
    return () => { cancelled = true; window.clearTimeout(timer); task?.cancel(); };
  }, [doc, page, x0, y0, x1, y1, zoom, pageSize.w, pageSize.h, width, height, renderKey]);

  if (!placement) return null;
  return (
    <div
      aria-hidden
      data-testid="source-magnifier"
      data-page={page}
      className="pointer-events-none absolute z-20 overflow-hidden rounded-2xl bg-white shadow-lg ring-2 ring-sky-300"
      style={{ ...placement, userSelect: "none", pointerEvents: "none" }}
    >
      <canvas ref={canvasRef} style={{ width: "100%", height: "100%", visibility: status === "ready" ? "visible" : "hidden" }} />
      {status === "error" ? <span className="absolute inset-0 flex items-center justify-center text-xs text-neutral-500">Magnifier unavailable</span> : null}
      <span className="absolute bottom-1 right-2 rounded bg-white/90 px-1 text-[10px] text-sky-700">2.5x</span>
    </div>
  );
}
