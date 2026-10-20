import { useEffect, useState } from "react";

import { documents, type DocumentIndex } from "./documents";

/** Refresh loaded readers when a complete replacement becomes authoritative. */
export function useDocumentIndex(slug: string | undefined, enabled = true) {
  return useDocumentIndexState(slug, enabled).index;
}

/**
 * The document's index, and whether the project no longer has the document
 * at all (deleted, or never ingested here): a card can then say so instead
 * of showing a page the browser still has cached.
 */
export function useDocumentIndexState(slug: string | undefined, enabled = true) {
  const [loaded, setLoaded] = useState<{ slug: string; index: DocumentIndex } | null>(null);
  const [missing, setMissing] = useState<string | null>(null);
  useEffect(() => {
    if (!slug || !enabled) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const index = await documents.index(slug);
        if (!cancelled) { setLoaded({ slug, index }); setMissing(null); }
      } catch (e) {
        if (!cancelled) {
          setLoaded(null);
          setMissing(String(e).includes("-> 404") ? slug : null);
        }
      } finally {
        // Match the explorer's existing cadence; do not overlap slow reads.
        if (!cancelled) timer = setTimeout(refresh, 8000);
      }
    };
    void refresh();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [slug, enabled]);
  return {
    index: enabled && loaded && loaded.slug === slug ? loaded.index : null,
    missing: enabled && !!slug && missing === slug,
  };
}
