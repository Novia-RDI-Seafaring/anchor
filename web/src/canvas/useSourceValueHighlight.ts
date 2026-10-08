import { useEffect, useState } from "react";

import { documents, refHasSelector, type ResolvableRef, type ResolvedRef } from "@/api/documents";

function validBox(box: number[] | undefined): box is number[] {
  return !!box && box.length === 4 && box.every(Number.isFinite)
    && box[0]! < box[2]! && box[1]! < box[3]!;
}

/** Text search refines a locator; it cannot establish which claim a value supports. */
export function useSourceValueHighlight(
  slug: string | undefined,
  page: number,
  ref: (ResolvableRef & { query?: string }) | null,
  generation: string | undefined,
  ready: boolean,
) {
  const key = ref && ref.slug === slug && ref.page === page
    ? JSON.stringify([slug, page, generation, ref.region_id, ref.item_id, ref.cell, ref.bbox, ref.query])
    : null;
  const [resolution, setResolution] = useState<{ key: string; ref: ResolvedRef | null } | null>(null);
  const [located, setLocated] = useState<{ key: string; quads: number[][] } | null>(null);
  const needsResolution = refHasSelector(ref);
  const resolved = resolution?.key === key ? resolution.ref : null;
  const resolvedBbox = resolved?.bbox;
  // Region boxes remain coarse even when only one identical value happens to
  // be searchable. Item/cell identity is certified by the existing resolver.
  // A standalone explicit box is itself a locator, without a region fallback.
  const clip = needsResolution
    ? resolved && (resolved.precision === "cell" || resolved.precision === "item") ? resolved.bbox : undefined
    : !ref?.region_id ? ref?.bbox : undefined;
  const precise = validBox(clip);

  useEffect(() => {
    if (!key || !ref || !slug || !needsResolution) return;
    let cancelled = false;
    documents.resolveRef(slug, ref)
      .then((answer) => { if (!cancelled) setResolution({ key, ref: answer }); })
      .catch(() => { if (!cancelled) setResolution({ key, ref: null }); });
    return () => { cancelled = true; };
  }, [key, slug, needsResolution]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!key || !slug || !ready || !ref?.query?.trim() || !precise || !clip) return;
    let cancelled = false;
    documents.locate(slug, page, ref.query, clip)
      .then((quads) => {
        if (cancelled) return;
        // Refuse multiple matches and out-of-scope results. A first-match
        // choice would silently turn an ambiguous search into exact evidence.
        const scoped = quads.filter((box) => validBox(box)
          && box[0]! >= clip[0]! && box[1]! >= clip[1]!
          && box[2]! <= clip[2]! && box[3]! <= clip[3]!);
        setLocated({ key, quads: scoped.length === quads.length ? scoped : [] });
      })
      .catch(() => { if (!cancelled) setLocated({ key, quads: [] }); });
    return () => { cancelled = true; };
  }, [key, slug, page, ready, precise, clip]); // eslint-disable-line react-hooks/exhaustive-deps

  const matches = ready && key && located?.key === key && precise ? located.quads : [];
  const hasQuery = ready && !!key && !!ref?.query?.trim();
  const status = !hasQuery ? null
    : needsResolution && resolution?.key !== key ? "Resolving source..."
    : !precise ? "Coarse source: exact value not identified."
    : located?.key !== key ? "Locating source value..."
    : matches.length > 1 ? "Ambiguous source: multiple matching values."
    : matches.length === 0 ? "Exact source value not located."
    : null;
  return { resolvedBbox, valueQuads: matches.length === 1 ? matches : [], status };
}
