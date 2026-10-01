/**
 * PictureHighlights — a hovered reference, lit on any picture cut from its
 * page.
 *
 * Two kinds of element show a section of a document as a picture: the
 * picture element itself, and a spec card dragged from a section, whose
 * header shows the section. Both are the page cut to a bbox, so whatever a
 * hovered reference points at on that page can be lit on them by mapping its
 * box into the cut. One hook, one overlay, used by both, so a value's anchor
 * lights the drawing, the table and the source viewer alike.
 */
import { useEffect, useState } from "react";

import { documents } from "@/api/documents";
import { boxesOnPicture, isOwnHover, type PictureBox } from "@/canvas/sourceHighlight";
import { useUiStore } from "@/stores/uiStore";

export type PictureCut = { slug?: string; page?: number; bbox?: number[]; region_id?: string };

/** The boxes to light on a picture cut from `cut`, for whatever is hovered now. */
export function usePictureHighlights(cut: PictureCut | null): PictureBox[] {
  const hovered = useUiStore((s) => s.hoveredSourceRef);
  const [resolved, setResolved] = useState<number[] | null>(null);
  const usable =
    !!cut && typeof cut.slug === "string" && typeof cut.page === "number" && Array.isArray(cut.bbox) && cut.bbox.length === 4;
  const onPage = usable && !!hovered && hovered.slug === cut!.slug && hovered.page === cut!.page;
  // The picture's own hover (the section itself, nothing below it) is not
  // lit: it would draw a box round the whole picture.
  const own = onPage && isOwnHover(cut!, hovered!);
  const key = onPage
    ? `${hovered!.slug}|${hovered!.page}|${hovered!.region_id ?? ""}|${hovered!.cell?.row ?? ""}|${hovered!.cell?.col ?? ""}|${hovered!.item_id ?? ""}`
    : null;
  useEffect(() => {
    // The last cell's box stays until the next one is known, so the mark
    // travels from one to the other instead of blinking out on the way.
    if (!key || !hovered || hovered.bbox || own) {
      setResolved(null);
      return undefined;
    }
    // A cell or an item carries no box of its own; the server knows it.
    let cancelled = false;
    void documents
      .resolveRef(hovered.slug, {
        page: hovered.page,
        region_id: hovered.region_id,
        item_id: hovered.item_id,
        cell: hovered.cell ?? undefined,
      })
      .then((r) => {
        if (!cancelled && r && r.page === hovered.page) setResolved(r.bbox);
      });
    return () => {
      cancelled = true;
    };
    // `key` carries everything the request depends on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, own]);
  if (!onPage || own) return [];
  return boxesOnPicture({ page: cut!.page!, bbox: cut!.bbox! }, [
    // Keyed by kind: the main mark goes to the next main mark, each extra
    // place to the next extra place, the way the source viewer pairs them.
    ...(hovered!.bbox ? [{ page: hovered!.page, bbox: hovered!.bbox, key: "main" }] : []),
    ...(resolved && !hovered!.bbox ? [{ page: hovered!.page, bbox: resolved, key: "main" }] : []),
    ...(hovered!.places ?? []).map((pl, i) => ({ ...pl, key: `also-${i}` })),
  ]);
}

/** The lit boxes, drawn over a picture that fills its (relative) container. */
export function PictureHighlightBoxes({ boxes }: { boxes: PictureBox[] }) {
  return (
    <>
      {boxes.map((b, i) => (
        <div
          key={b.key ?? i}
          data-testid="image-source-highlight"
          className="anchor-mark-fade anchor-mark-flying pointer-events-none absolute rounded-sm border-2 border-amber-500 bg-amber-300/30"
          style={{
            left: `calc(${b.left}% - 3px)`,
            top: `calc(${b.top}% - 3px)`,
            width: `calc(${b.width}% + 6px)`,
            height: `calc(${b.height}% + 6px)`,
          }}
        />
      ))}
    </>
  );
}
