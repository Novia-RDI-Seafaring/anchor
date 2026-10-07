/**
 * regionDrop.ts — what a section of a document becomes when it is dragged
 * onto the canvas.
 *
 * One rule for both places a section can be dragged from: the document
 * card's page preview and the source dock. A table or a paragraph becomes a
 * spec card anchored to its bbox, as it always did. A diagram or a figure
 * becomes a picture, cut from the page by that bbox, since a drawing shown
 * as a card of empty rows was the reason the old canvas could not "drag the
 * image over": it could, and what arrived was not an image.
 */
import type { Region } from "@/api/documents";

export type DropPayload = {
  node_type: string;
  label: string;
  width?: number;
  data: Record<string, unknown>;
};

/** Region kinds that are pictures rather than text or tables. */
const PICTURE_KINDS = new Set(["diagram", "figure", "image", "picture", "drawing", "chart"]);

export function isPictureRegion(region: Region): boolean {
  return PICTURE_KINDS.has(String(region.kind ?? "").toLowerCase());
}

export function regionDropPayload(args: {
  slug: string;
  page: number;
  region: Region;
  /** The document card the section was dragged from, if any: the drop joins them. */
  documentNodeId?: string;
}): DropPayload | null {
  const { slug, page, region, documentNodeId } = args;
  const bbox = region.bbox ?? region.approximate_bbox;
  if (!bbox || bbox.length !== 4) return null;
  const rid = region.id ?? "";
  const label = region.title ?? region.kind ?? rid;
  const source_ref = {
    slug,
    coord_origin: "top-left",
    kind: "pdf-page-bbox",
    page,
    bbox,
    ...(rid ? { region_id: rid } : {}),
  };
  const common = {
    source_doc_slug: slug,
    ...(documentNodeId ? { source_doc_node_id: documentNodeId } : {}),
    ...(rid ? { source_region_id: rid } : {}),
    source_ref,
  };
  if (isPictureRegion(region)) {
    return {
      node_type: "image",
      label,
      width: 320,
      data: { label, width: 320, ...common },
    };
  }
  // Wide enough that the section's picture on the card can be read: a
  // thirteen-column table at a card's default width was a strip of grey.
  // And no description as body text: for a table it is the table again,
  // flattened into a paragraph, under a picture of the table.
  const width = Math.round(Math.min(900, Math.max(360, (bbox[2]! - bbox[0]!) * 1.6)));
  return {
    node_type: "spec",
    label,
    width,
    data: {
      ...common,
      width,
      crops: region.crops,
      tags: (region as { tags?: string[] }).tags ?? [],
    },
  };
}
