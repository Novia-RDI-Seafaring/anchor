import type { Node } from "@xyflow/react";

import type { KBDocument } from "@/contexts/AppContext";

import type { PDFHighlight } from "./PDFModal";
import type { CanvasItem } from "./canvas-model";

export interface Relation {
  from_id: string;
  to_id: string;
  label: string;
  source_handle?: string;
  target_handle?: string;
  document_id?: string;
  page?: number;
  bbox?: number[];
  highlights?: PDFHighlight[];
}

export interface FlowPosition {
  x: number;
  y: number;
}

interface ProvenanceInput {
  id: string;
  parent_id?: string;
}

const SOURCE_COLORS = ["#ef4444", "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6", "#ec4899", "#14b8a6", "#f97316"];

export const NODE_SIZE: Record<string, { w: number; h: number }> = {
  conceptNode: { w: 240, h: 60 },
  entityNode: { w: 280, h: 70 },
  categoryNode: { w: 220, h: 55 },
  topicNode: { w: 240, h: 60 },
  factNode: { w: 280, h: 100 },
  documentNode: { w: 150, h: 64 },
  sourceNode: { w: 180, h: 40 },
  specNode: { w: 420, h: 200 },
  fmuNode: { w: 280, h: 200 },
  plotNode: { w: 320, h: 220 },
  imageNode: { w: 300, h: 200 },
  funnelNode: { w: 120, h: 90 },
  modelNode: { w: 200, h: 72 },
  areaNode: { w: 600, h: 400 },
  squareShapeNode: { w: 150, h: 150 },
  circleShapeNode: { w: 160, h: 160 },
  diamondShapeNode: { w: 150, h: 150 },
  noteNode: { w: 200, h: 200 },
  richTextNode: { w: 280, h: 60 },
};

export const DEFAULT_SIZE = { w: 220, h: 80 };
export const DOCUMENT_NODE_SIZE = { w: 150, h: 64 };
export const KNOWLEDGE_FILE_PATTERN = /\.(pdf|docx|txt|md|html)$/i;

export function anchorAtCenter(position: FlowPosition, size: { w: number; h: number }): FlowPosition {
  return {
    x: position.x - size.w / 2,
    y: position.y - size.h / 2,
  };
}

export function inferNodeSize(node: Node): { w: number; h: number } {
  const width =
    typeof node.width === "number"
      ? node.width
      : typeof node.measured?.width === "number"
        ? node.measured.width
        : typeof node.style?.width === "number"
          ? node.style.width
          : NODE_SIZE[node.type ?? ""]?.w ?? DEFAULT_SIZE.w;
  const height =
    typeof node.height === "number"
      ? node.height
      : typeof node.measured?.height === "number"
        ? node.measured.height
        : typeof node.style?.height === "number"
          ? node.style.height
          : NODE_SIZE[node.type ?? ""]?.h ?? DEFAULT_SIZE.h;
  return { w: width, h: height };
}

export function findBestAreaParent(
  absolutePosition: FlowPosition,
  nodeSize: { w: number; h: number },
  nodes: Node[],
  excludeNodeId?: string,
): { id: string; position: FlowPosition } | null {
  let bestParent: { id: string; ratio: number; position: FlowPosition } | null = null;

  for (const candidate of nodes) {
    if (candidate.type !== "areaNode" || candidate.id === excludeNodeId) continue;
    const areaSize = inferNodeSize(candidate);
    const overlapWidth = Math.max(
      0,
      Math.min(absolutePosition.x + nodeSize.w, candidate.position.x + areaSize.w) - Math.max(absolutePosition.x, candidate.position.x),
    );
    const overlapHeight = Math.max(
      0,
      Math.min(absolutePosition.y + nodeSize.h, candidate.position.y + areaSize.h) - Math.max(absolutePosition.y, candidate.position.y),
    );
    const overlapRatio = (overlapWidth * overlapHeight) / Math.max(1, nodeSize.w * nodeSize.h);
    if (overlapRatio > 0.5 && (!bestParent || overlapRatio > bestParent.ratio)) {
      bestParent = {
        id: candidate.id,
        ratio: overlapRatio,
        position: {
          x: absolutePosition.x - candidate.position.x,
          y: absolutePosition.y - candidate.position.y,
        },
      };
    }
  }

  return bestParent ? { id: bestParent.id, position: bestParent.position } : null;
}

export function buildSourceColorMap(workspaceDocIds: string[]): Map<string, string> {
  const map = new Map<string, string>();
  workspaceDocIds.forEach((docId, index) => {
    map.set(`__doc_${docId}`, SOURCE_COLORS[index % SOURCE_COLORS.length]!);
  });
  return map;
}

export function computeNodeSources(
  nodes: ProvenanceInput[],
  relations: { from_id: string; to_id: string }[],
): Map<string, Set<string>> {
  const inbound = new Map<string, string[]>();
  for (const relation of relations) {
    const predecessors = inbound.get(relation.to_id) ?? [];
    predecessors.push(relation.from_id);
    inbound.set(relation.to_id, predecessors);
  }

  const parentOf = new Map<string, string>();
  for (const node of nodes) {
    if (node.parent_id) parentOf.set(node.id, node.parent_id);
  }

  const cache = new Map<string, Set<string>>();

  function walk(nodeId: string, visited: Set<string>): Set<string> {
    if (cache.has(nodeId)) return cache.get(nodeId)!;
    if (visited.has(nodeId)) return new Set();
    visited.add(nodeId);

    const sources = new Set<string>();
    if (nodeId.startsWith("__doc_")) {
      sources.add(nodeId);
      cache.set(nodeId, sources);
      return sources;
    }

    for (const predecessor of inbound.get(nodeId) ?? []) {
      for (const source of walk(predecessor, visited)) sources.add(source);
    }

    const parent = parentOf.get(nodeId);
    if (parent) {
      for (const source of walk(parent, visited)) sources.add(source);
    }

    cache.set(nodeId, sources);
    return sources;
  }

  const result = new Map<string, Set<string>>();
  for (const node of nodes) {
    result.set(node.id, walk(node.id, new Set()));
  }

  for (const relation of relations) {
    for (const nodeId of [relation.from_id, relation.to_id]) {
      if (!result.has(nodeId) && nodeId.startsWith("__doc_")) {
        result.set(nodeId, new Set([nodeId]));
      }
    }
  }

  return result;
}

export function pickEdgeSourceColor(
  sourceNodeSources: Set<string> | undefined,
  colorMap: Map<string, string>,
): string | null {
  if (!sourceNodeSources || sourceNodeSources.size === 0) return null;
  for (const docNodeId of sourceNodeSources) {
    const color = colorMap.get(docNodeId);
    if (color) return color;
  }
  return null;
}

export function buildDerivedEvidenceRelations(
  nodes: CanvasItem[],
  relations: Relation[],
  documents: KBDocument[],
): Relation[] {
  const existing = new Set(
    relations.map((relation) => `${relation.from_id}>${relation.to_id}>${relation.source_handle ?? ""}>${relation.target_handle ?? ""}`),
  );
  const filenameToDocNode = new Map(documents.map((doc) => [doc.filename, `__doc_${doc.document_id}`]));
  const filenameToDocId = new Map(documents.map((doc) => [doc.filename, doc.document_id]));
  const stemToDocNode = new Map(documents.map((doc) => [doc.filename.replace(/\.pdf$/i, ""), `__doc_${doc.document_id}`]));
  const stemToDocId = new Map(documents.map((doc) => [doc.filename.replace(/\.pdf$/i, ""), doc.document_id]));
  const derived: Relation[] = [];
  const seen = new Set<string>();

  const addEvidence = (
    fromId: string,
    source: {
      doc_id?: string;
      filename?: string;
      page?: number;
      bbox?: number[];
      highlights?: PDFHighlight[];
    },
    targetHandle?: string,
  ) => {
    let docNodeId = source.doc_id
      ? `__doc_${source.doc_id}`
      : source.filename
        ? filenameToDocNode.get(source.filename)
        : undefined;
    let resolvedDocId = source.doc_id || (source.filename ? filenameToDocId.get(source.filename) : undefined);

    if (!docNodeId && source.filename) {
      const stem = source.filename.replace(/\.pdf$/i, "");
      for (const [knownStem, nodeId] of stemToDocNode) {
        if (stem.startsWith(knownStem) || knownStem.startsWith(stem)) {
          docNodeId = nodeId;
          resolvedDocId = stemToDocId.get(knownStem);
          break;
        }
      }
    }
    if (!docNodeId || docNodeId === fromId) return;

    const key = `${fromId}>${docNodeId}>doc-evidence-out>${targetHandle ?? ""}`;
    if (existing.has(key) || seen.has(key)) return;
    seen.add(key);

    const page = typeof source.page === "number" ? source.page : 0;
    const bbox = Array.isArray(source.bbox) ? source.bbox : [];
    const highlights =
      Array.isArray(source.highlights) && source.highlights.length > 0
        ? source.highlights
        : page > 0 && bbox.length === 4
          ? [{ page, bbox }]
          : [];

    derived.push({
      from_id: fromId,
      to_id: docNodeId,
      label: page > 0 ? `p.${page}` : "",
      source_handle: targetHandle,
      target_handle: "doc-evidence-out",
      document_id: resolvedDocId,
      page,
      bbox,
      highlights,
    });
  };

  for (const node of nodes) {
    if (node.id.startsWith("__doc_")) continue;

    if (Array.isArray(node.parameter_sections)) {
      node.parameter_sections.forEach((section, sectionIndex) => {
        (section.rows ?? []).forEach((row, rowIndex) => {
          if (row?.source) addEvidence(node.id, row.source, `spec-row-in-${sectionIndex}-${rowIndex}`);
        });
      });
    }

    if (Array.isArray(node.properties)) {
      node.properties.forEach((property, propertyIndex) => {
        addEvidence(
          node.id,
          {
            filename: property?.ref_filename,
            page: property?.ref_page,
            bbox: property?.ref_bbox,
            highlights: property?.ref_highlights as PDFHighlight[] | undefined,
          },
          `spec-prop-in-${propertyIndex}`,
        );
      });
    }

    if (node.filename && !node.id.startsWith("__doc_")) {
      addEvidence(node.id, {
        filename: node.filename,
        page: node.page,
        bbox: node.bbox,
        highlights: node.highlights as PDFHighlight[] | undefined,
      });
    }
  }

  return derived;
}
