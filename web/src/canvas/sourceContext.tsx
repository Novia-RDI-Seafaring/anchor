/**
 * Every source of the card in view at once.
 *
 * Every row's source is shown at once, faintly, and the one the reader is on
 * is shown fully; moving between rows only changes which is strong. A ref
 * with no card around it (a link in prose) has one highlight that travels. The quoted words of a source are
 * underlined the first time its anchor is hovered, drawn as a pen draws
 * them, and stay drawn after that, fading with their source.
 */
import { useEffect, useState, type CSSProperties } from "react";

import { documents, type ResolvableRef } from "@/api/documents";
import { SourceMark } from "@/canvas/SourceMark";
import { boxesOnPage, quoteBoxes } from "@/canvas/quotes";

/** One source of the card, placed: where it is and its quoted words. */
export type ContextPlace = {
  key: string;
  page: number;
  bbox?: number[];
  quotes: { page: number; boxes: number[][] }[];
};

/** A stable identity for a ref: the same source gives the same key. */
export function refKey(ref: ResolvableRef | null | undefined): string {
  if (!ref) return "";
  const quotes = (ref.quotes ?? []).map((q) => (typeof q === "string" ? q : q.exact));
  return JSON.stringify([ref.slug, ref.page, ref.region_id, ref.item_id, ref.cell, ref.bbox, quotes]);
}

/** Places already looked up, kept for the session. */
const placed = new Map<string, ContextPlace | null>();
const pending = new Map<string, Promise<void>>();

async function place(ref: ResolvableRef): Promise<ContextPlace | null> {
  if (!ref.slug || !ref.page) return null;
  const answer = await documents.resolveRef(ref.slug, ref).catch(() => null);
  const page = answer?.page ?? ref.page;
  return {
    key: refKey(ref),
    page,
    bbox: answer?.bbox ?? ref.bbox,
    quotes: quoteBoxes(ref.quotes, ref.page, answer?.quotes),
  };
}

/**
 * Every ref placed. Places already looked up are returned at once, on the
 * first render of a hover: waiting a beat for them let the travelling
 * highlight draw in the meantime, and its underlines drew afresh every time.
 */
export function useContextPlaces(refs: ResolvableRef[] | undefined): ContextPlace[] {
  const keys = (refs ?? []).map(refKey);
  const key = JSON.stringify(keys);
  const [, setVersion] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const missing = (refs ?? []).filter((ref) => !placed.has(refKey(ref)));
    void Promise.all(missing.map((ref) => {
      const k = refKey(ref);
      if (!pending.has(k)) {
        pending.set(k, place(ref).then((p) => { placed.set(k, p); pending.delete(k); }));
      }
      return pending.get(k)!;
    })).then(() => { if (!cancelled && missing.length) setVersion((v) => v + 1); });
    return () => { cancelled = true; };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return keys.map((k) => placed.get(k)).filter((p): p is ContextPlace => !!p);
}

/** Sources whose underlines have been drawn once this session. */
const drawn = new Set<string>();

/**
 * An underline that draws itself the first time its source is the active
 * one, and is simply there every time after.
 */
function Underline({ id, box, order, faint }: {
  id: string; box: CSSProperties; order: number; faint: boolean;
}) {
  const [fresh] = useState(() => !drawn.has(id));
  useEffect(() => { drawn.add(id); }, [id]);
  return (
    <SourceMark
      data-testid="context-underline"
      flying={false}
      className={`z-10 anchor-mark-underline${fresh ? "" : " anchor-mark-drawn"}${faint ? " anchor-mark-faint" : ""}`}
      box={{ ...box, "--mark-i": order, "--underline-wait": "120ms" } as CSSProperties}
    />
  );
}

/**
 * Draw every place on the given pages: the active one fully, the rest
 * faintly. `toBox` turns a page box into the caller's layout, or null when
 * that page is not shown.
 */
export function ContextMarks({ places, active, pages, toBox }: {
  places: ContextPlace[];
  active: string | undefined;
  pages: number[];
  toBox: (page: number, bbox: number[]) => CSSProperties | null;
}) {
  return (
    <>
      {places.flatMap((p) => {
        const faint = p.key !== active;
        const out = [];
        const wash = p.bbox ? toBox(p.page, p.bbox) : null;
        if (wash && pages.includes(p.page)) {
          out.push(
            <SourceMark
              key={`wash:${p.key}`}
              data-testid="context-wash"
              data-active={faint ? undefined : "true"}
              flying={false}
              className={`z-10${faint ? " anchor-mark-faint" : ""}`}
              box={wash}
            />,
          );
        }
        // Underlines appear once their source has been the active one.
        if (faint && !drawn.has(p.key)) return out;
        for (const page of pages) {
          boxesOnPage(p.quotes, page).forEach((bbox, i) => {
            const box = toBox(page, bbox);
            if (box) out.push(<Underline key={`u:${p.key}:${page}:${i}`} id={p.key} box={box} order={i} faint={faint} />);
          });
        }
        return out;
      })}
    </>
  );
}
