export const EVIDENCE_EDGE_STROKE = "#059669";
export const EVIDENCE_EDGE_ACTIVE_STROKE = "#10b981";
export const EVIDENCE_EDGE_QUIET_WIDTH = 1.25;
export const EVIDENCE_EDGE_ACTIVE_WIDTH = 3;
export const EVIDENCE_EDGE_QUIET_OPACITY = 0.55;

type EdgeVisualData = {
  kind?: string | null;
  active?: boolean;
  dimmed?: boolean;
} & Record<string, unknown>;

export function evidenceStrokeWidth(active: boolean): number {
  return active ? EVIDENCE_EDGE_ACTIVE_WIDTH : EVIDENCE_EDGE_QUIET_WIDTH;
}

export function isDimmedEvidence(data: unknown): boolean {
  return isEvidenceEdge(data) && (data as EdgeVisualData).dimmed === true;
}

export function isEvidenceEdge(data: unknown): data is EdgeVisualData {
  return !!data && typeof data === "object" && (data as EdgeVisualData).kind === "evidence";
}

export function isActiveEvidence(data: unknown): boolean {
  return isEvidenceEdge(data) && (data as EdgeVisualData).active === true;
}

export function evidenceStroke(data: unknown): string {
  return isActiveEvidence(data) ? EVIDENCE_EDGE_ACTIVE_STROKE : EVIDENCE_EDGE_STROKE;
}
