import { useEffect, useId, useMemo, useState } from "react";

import { documents, type DocumentIndex } from "@/api/documents";

import { embeddedContents, indexedObjects, silverContents, type ContentsEntry } from "./pdfContents";
import type { PdfDoc } from "./pdfjs";

type Props = {
  slug: string;
  generation?: string;
  page: number;
  total: number;
  index?: DocumentIndex | null;
  /** Reuse the continuous viewer's PDF; undefined lets quick-look load lazily. */
  pdf?: PdfDoc | null;
  initialTab?: "pages" | "contents";
  onNavigate: (entry: ContentsEntry) => void;
};

function Entries({ entries, page, onNavigate }: Pick<Props, "page" | "onNavigate"> & { entries: ContentsEntry[] }) {
  return (
    <ul className="space-y-1">
      {entries.map((entry, i) => (
        <li key={`${i}:${entry.title}`}>
          {entry.page ? (
            <button
              type="button"
              onClick={() => onNavigate(entry)}
              aria-current={entry.page === page ? "page" : undefined}
              className={`flex w-full items-start gap-2 rounded px-2 py-1 text-left text-xs ${entry.page === page ? "bg-sky-100 text-sky-900" : "hover:bg-neutral-200"}`}
            >
              <span className="min-w-0 flex-1 break-words">{entry.title}</span>
              <span className="shrink-0 tabular-nums text-neutral-500">{entry.page}</span>
            </button>
          ) : <span className="block px-2 py-1 text-xs font-medium">{entry.title}</span>}
          {entry.children.length ? (
            <div className="ml-3 border-l border-neutral-200 pl-1">
              <Entries entries={entry.children} page={page} onNavigate={onNavigate} />
            </div>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

/** Shared page and contents navigation for the dock and full-screen quick-look. */
export function PdfNavigationRail({ slug, generation, page, total, index, pdf, initialTab = "pages", onNavigate }: Props) {
  const [tab, setTab] = useState(initialTab);
  const id = useId();
  const outline = useMemo(() => silverContents(index, total), [index, total]);
  const tables = useMemo(() => indexedObjects(index?.tables, "Table", total), [index, total]);
  const figures = useMemo(() => indexedObjects(index?.figures, "Figure", total), [index, total]);
  const needsEmbedded = tab === "contents" && outline.length === 0;
  const [embedded, setEmbedded] = useState<ContentsEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setEmbedded([]);
    setLoading(false);
    if (!needsEmbedded || pdf === null) return;
    let cancelled = false;
    let destroy: (() => Promise<void>) | undefined;
    setLoading(true);
    void (async () => {
      try {
        let doc = pdf;
        if (!doc) {
          const { loadPdf } = await import("./pdfjs");
          if (cancelled) return;
          const loaded = await loadPdf(documents.pdfUrl(slug, generation));
          destroy = loaded.destroy;
          if (cancelled) { void destroy(); return; }
          doc = loaded.doc;
        }
        const tree = await embeddedContents(doc);
        if (!cancelled) setEmbedded(tree);
      } catch {
        // Missing or unreadable bookmarks leave Pages as the fallback.
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; if (destroy) void destroy(); };
  }, [slug, generation, pdf, needsEmbedded]);

  const headings = outline.length ? outline : embedded;
  return (
    <nav aria-label="PDF navigation" className={`${tab === "pages" ? "w-[120px]" : "w-56"} flex shrink-0 flex-col border-r border-neutral-200 bg-neutral-50 text-neutral-700`}>
      <div role="tablist" aria-label="PDF navigation" className="flex shrink-0 border-b border-neutral-200">
        {(["pages", "contents"] as const).map((name) => (
          <button
            key={name}
            id={`${id}-${name}`}
            role="tab"
            type="button"
            aria-selected={tab === name}
            aria-controls={`${id}-panel`}
            tabIndex={tab === name ? 0 : -1}
            onClick={() => setTab(name)}
            onKeyDown={(event) => {
              if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
              event.preventDefault();
              const next = event.key === "Home" ? "pages" : event.key === "End" ? "contents" : name === "pages" ? "contents" : "pages";
              setTab(next);
              document.getElementById(`${id}-${next}`)?.focus();
            }}
            className={`flex-1 px-1 py-2 text-xs ${tab === name ? "border-b-2 border-sky-500 font-medium" : "hover:bg-neutral-200"}`}
          >{name === "pages" ? "Pages" : "Contents"}</button>
        ))}
      </div>
      <div id={`${id}-panel`} role="tabpanel" aria-labelledby={`${id}-${tab}`} tabIndex={0} className="min-h-0 flex-1 overflow-y-auto p-2">
        {tab === "pages" ? (
          <ul data-testid="thumbnail-rail" className="flex flex-col gap-2">
            {Array.from({ length: total }, (_, i) => i + 1).map((target) => (
              <li key={target}>
                <button type="button" data-testid="thumbnail" data-page={target}
                  aria-current={target === page ? "page" : undefined}
                  onClick={() => onNavigate({ title: `Page ${target}`, page: target, children: [] })}
                  className={`block w-full rounded border bg-white p-0.5 text-center ${target === page ? "border-sky-500 ring-2 ring-sky-300" : "border-neutral-300 hover:border-neutral-400"}`}>
                  <img src={documents.pageImageUrl(slug, target, generation)} alt={`Page ${target}`} loading="lazy" width={96} className="mx-auto block h-auto w-full" />
                  <span className="block py-0.5 text-[10px] tabular-nums text-neutral-500">{target}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <>
            <Entries entries={headings} page={page} onNavigate={onNavigate} />
            {loading || (needsEmbedded && pdf === null) ? <p role="status" className="p-2 text-xs text-neutral-500">Loading contents...</p> : null}
            {!headings.length && !tables.length && !figures.length && !loading && pdf !== null ? (
              <p className="p-2 text-xs text-neutral-500">No contents available. Use Pages to browse this document.</p>
            ) : null}
            {([{ title: "Tables", entries: tables }, { title: "Figures", entries: figures }]).map((group) => group.entries.length ? (
              <section key={group.title} aria-label={group.title}>
                <h3 className="px-2 pb-1 pt-3 text-xs font-semibold">{group.title}</h3>
                <Entries entries={group.entries} page={page} onNavigate={onNavigate} />
              </section>
            ) : null)}
          </>
        )}
      </div>
    </nav>
  );
}
