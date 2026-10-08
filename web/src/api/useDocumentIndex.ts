import { useEffect, useState } from "react";

import { documents, type DocumentIndex } from "./documents";

/** Refresh loaded readers when a complete replacement becomes authoritative. */
export function useDocumentIndex(slug: string | undefined, enabled = true) {
  const [loaded, setLoaded] = useState<{ slug: string; index: DocumentIndex } | null>(null);
  useEffect(() => {
    if (!slug || !enabled) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const index = await documents.index(slug);
        if (!cancelled) setLoaded({ slug, index });
      } catch {
        if (!cancelled) setLoaded(null);
      } finally {
        // Match the explorer's existing cadence; do not overlap slow reads.
        if (!cancelled) timer = setTimeout(refresh, 8000);
      }
    };
    void refresh();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [slug, enabled]);
  return enabled && loaded && loaded.slug === slug ? loaded.index : null;
}
