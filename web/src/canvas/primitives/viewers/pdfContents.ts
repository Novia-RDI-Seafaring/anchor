import type { DocumentIndex } from "@/api/documents";

import type { PdfDoc } from "./pdfjs";

export type ContentsEntry = {
  title: string;
  page?: number;
  bbox?: number[];
  children: ContentsEntry[];
};

function validPage(page: unknown, total: number): page is number {
  return typeof page === "number" && Number.isInteger(page) && page >= 1 && page <= total;
}

function validBbox(bbox: unknown): number[] | undefined {
  if (!Array.isArray(bbox) || bbox.length !== 4 || !bbox.every(Number.isFinite)) return undefined;
  return bbox[0] <= bbox[2] && bbox[1] <= bbox[3] ? bbox : undefined;
}

/** Silver headings are ordered flat records with explicit nesting levels. */
export function silverContents(index: DocumentIndex | null | undefined, total: number): ContentsEntry[] {
  const roots: ContentsEntry[] = [];
  const stack: Array<{ level: number; entry: ContentsEntry }> = [];
  for (const heading of index?.outline ?? []) {
    if (!heading.title?.trim() || !validPage(heading.page, total)) continue;
    const level = Number.isFinite(heading.level) ? heading.level : 1;
    const entry: ContentsEntry = {
      title: heading.title.trim(), page: heading.page, bbox: validBbox(heading.bbox), children: [],
    };
    while (stack.length && stack[stack.length - 1]!.level >= level) stack.pop();
    (stack[stack.length - 1]?.entry.children ?? roots).push(entry);
    stack.push({ level, entry });
  }
  return roots;
}

export function indexedObjects(
  objects: Array<Record<string, unknown>> | undefined,
  kind: "Table" | "Figure",
  total: number,
): ContentsEntry[] {
  return (objects ?? []).flatMap((object, i) => {
    if (!validPage(object.page, total)) return [];
    const caption = typeof object.caption === "string" ? object.caption.trim() : "";
    return [{ title: `${kind} ${i + 1}${caption ? `: ${caption}` : ""}`, page: object.page,
      bbox: validBbox(object.bbox), children: [] }];
  });
}

/** PDF destinations use a zero-based page index or an indirect page ref. */
export async function embeddedContents(doc: Pick<PdfDoc, "getOutline" | "getDestination" | "getPageIndex" | "numPages">): Promise<ContentsEntry[]> {
  type Bookmark = Awaited<ReturnType<PdfDoc["getOutline"]>>[number];
  async function entries(bookmarks: Bookmark[]): Promise<ContentsEntry[]> {
    return Promise.all(bookmarks.map(async (bookmark) => {
      let page: number | undefined;
      try {
        const dest = typeof bookmark.dest === "string"
          ? await doc.getDestination(bookmark.dest) : bookmark.dest;
        if (Array.isArray(dest) && dest.length) {
          const target: unknown = dest[0];
          const zeroBased = typeof target === "number" ? target
            : target && typeof target === "object" && "num" in target && "gen" in target
              ? await doc.getPageIndex(target as { num: number; gen: number }) : NaN;
          if (validPage(zeroBased + 1, doc.numPages)) page = zeroBased + 1;
        }
      } catch {
        // One broken or external bookmark must not discard the remaining tree.
      }
      return { title: bookmark.title.trim(), page, children: await entries(bookmark.items ?? []) };
    })).then((tree) => tree.filter((entry) => entry.title && (entry.page || entry.children.length)));
  }
  return entries(await doc.getOutline() ?? []);
}
