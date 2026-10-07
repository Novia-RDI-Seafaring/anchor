import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { documents, refHasSelector, type ResolvableRef } from "@/api/documents";

/**
 * RefHoverPreview — hover a source ref, see the source.
 *
 * Hovering an `anchor:` link used to do two weak things: show a native
 * `title` tooltip reading "Open <ref>", and light up the region in a document
 * card IF one happened to be placed, open and visible on the canvas. In every
 * other case the reader learned nothing about what was at the other end and
 * had to click, which navigates away from the sentence they were reading.
 *
 * This shows the referenced place itself: a crop of the page around it, with
 * the referenced part boxed inside so it reads as a located excerpt rather
 * than a floating picture. That is the promise the whole application makes --
 * checking a claim should be a glance.
 *
 * Precision matters here. A ref that points below the region (one table cell,
 * one silver item) is resolved first, so the box lands on the cell rather than
 * the section it sits in. The crop is the referenced box plus a margin, so
 * there is enough page around it to see WHERE it came from.
 *
 * Timing is deliberate. An open delay stops a panel strobing as the cursor
 * sweeps a paragraph; a close delay lets the pointer travel from the link into
 * the panel without it vanishing underneath.
 *
 * Rendered through a portal to <body>. The link lives inside React Flow's
 * transformed viewport, and `position: fixed` inside a transformed ancestor
 * resolves against that ancestor rather than the window -- so without the
 * portal the panel is scaled by the canvas zoom (380px of design became 195px
 * at half zoom) and the fits-on-screen maths is measured against the wrong
 * box.
 */

/** Points of page to keep around the referenced box, for context. */
const CONTEXT_MARGIN_PT = 90;
/** Long enough not to fire on a sweep, short enough not to feel laggy. */
export const OPEN_DELAY_MS = 180;
/** Long enough to move the pointer from the link onto the panel. */
export const CLOSE_DELAY_MS = 140;

const PANEL_W = 380;
const GAP = 12;

type Box = { left: number; top: number; right: number; bottom: number };

export function expand(bbox: number[], margin = CONTEXT_MARGIN_PT): Box {
  const [l, t, r, b] = bbox as [number, number, number, number];
  return {
    // Clamped at the page origin; the renderer clamps the far edges, which it
    // has to do anyway because it alone knows the page size.
    left: Math.max(0, l - margin),
    top: Math.max(0, t - margin),
    right: r + margin,
    bottom: b + margin,
  };
}

/** Where the referenced box sits inside the crop, as CSS percentages. */
export function insetWithin(bbox: number[], crop: Box) {
  const [l, t, r, b] = bbox as [number, number, number, number];
  const w = crop.right - crop.left;
  const h = crop.bottom - crop.top;
  if (w <= 0 || h <= 0) return null;
  const pct = (v: number) => `${Math.max(0, Math.min(100, v * 100))}%`;
  return {
    left: pct((l - crop.left) / w),
    top: pct((t - crop.top) / h),
    width: pct((r - l) / w),
    height: pct((b - t) / h),
  };
}

export function RefHoverPreview({
  refValue,
  anchorRect,
  onPointerEnter,
  onPointerLeave,
}: {
  refValue: ResolvableRef;
  /** Bounding rect of the link, in viewport coordinates. */
  anchorRect: DOMRect;
  onPointerEnter?: () => void;
  onPointerLeave?: () => void;
}) {
  const [bbox, setBbox] = useState<number[] | null>(refValue.bbox ?? null);
  const [page, setPage] = useState<number | null>(refValue.page ?? null);
  const [precision, setPrecision] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);

  const slug = refValue.slug;

  // Resolve before cropping, for two reasons. A cell or item selector tightens
  // the box from the section down to the value. And a region-only ref -- the
  // common shape an `anchor:` link writes, `?page=2&region=r9` -- carries no
  // bbox at all, so without resolving it there is nothing to crop.
  useEffect(() => {
    const needsBox = !refValue.bbox && typeof refValue.region_id === "string";
    if (!slug || !(refHasSelector(refValue) || needsBox)) return;
    let cancelled = false;
    documents
      .resolveRef(slug, refValue)
      .then((r) => {
        if (cancelled || !r) return;
        if (r.bbox) setBbox(r.bbox);
        if (r.page) setPage(r.page);
        setPrecision(r.precision ?? null);
      })
      .catch(() => {
        /* keep the ref's own bbox: a coarse preview beats none */
      });
    return () => {
      cancelled = true;
    };
  }, [slug, refValue]);

  // Right of the link when it fits, left when it does not, clamped vertically.
  useLayoutEffect(() => {
    const h = panelRef.current?.offsetHeight ?? 260;
    const fitsRight = anchorRect.right + GAP + PANEL_W <= window.innerWidth;
    const left = fitsRight
      ? anchorRect.right + GAP
      : Math.max(GAP, anchorRect.left - GAP - PANEL_W);
    const top = Math.max(
      GAP,
      Math.min(window.innerHeight - h - GAP, anchorRect.top - 24),
    );
    setPos({ left, top });
  }, [anchorRect, bbox]);

  if (!slug || page == null || !bbox || bbox.length !== 4) return null;

  const crop = expand(bbox);
  const inset = insetWithin(bbox, crop);
  const src = documents.pageCropUrl(
    slug,
    page,
    [crop.left, crop.top, crop.right, crop.bottom],
    200,
  );

  return createPortal(
    <div
      ref={panelRef}
      data-testid="ref-hover-preview"
      role="tooltip"
      className="fixed z-50 overflow-hidden rounded-lg border border-neutral-300 bg-white shadow-xl"
      style={{ width: PANEL_W, left: pos?.left ?? -9999, top: pos?.top ?? -9999 }}
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
    >
      <div className="relative bg-neutral-50">
        {failed ? (
          <div className="px-3 py-6 text-center text-[11px] text-neutral-500">
            No preview for this page.
          </div>
        ) : (
          <>
            <img
              src={src}
              alt=""
              className="block w-full"
              data-testid="ref-hover-crop"
              onError={() => setFailed(true)}
            />
            {inset ? (
              <div
                aria-hidden
                data-testid="ref-hover-box"
                className="pointer-events-none absolute rounded-[2px]"
                style={{
                  ...inset,
                  background: "rgba(14, 165, 233, 0.16)",
                  boxShadow: "0 0 0 2px #0369A1",
                }}
              />
            ) : null}
          </>
        )}
      </div>
      <div className="flex items-center justify-between gap-2 border-t border-neutral-200 px-2 py-1 text-[10px] text-neutral-500">
        <span className="truncate">
          {slug} · page {page}
        </span>
        <span className="shrink-0 text-neutral-400">
          {precision ? `${precision} · ` : ""}click to open
        </span>
      </div>
    </div>,
    document.body,
  );
}
