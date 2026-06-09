export const EVIDENCE_EDGE_STROKE = "#059669";
export const EVIDENCE_EDGE_ACTIVE_STROKE = "#10b981";

type EdgeVisualData = {
  kind?: string | null;
  active?: boolean;
  dimmed?: boolean;
} & Record<string, unknown>;

type EndpointSocketProps = {
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  stroke: string;
  evidence: boolean;
  active: boolean;
};

export function isEvidenceEdge(data: unknown): data is EdgeVisualData {
  return !!data && typeof data === "object" && (data as EdgeVisualData).kind === "evidence";
}

export function isActiveEvidence(data: unknown): boolean {
  return isEvidenceEdge(data) && (data as EdgeVisualData).active === true;
}

export function evidenceStroke(data: unknown): string {
  return isActiveEvidence(data) ? EVIDENCE_EDGE_ACTIVE_STROKE : EVIDENCE_EDGE_STROKE;
}

export function EvidencePathUnderlay({
  path,
  evidence,
}: {
  path: string;
  evidence: boolean;
}) {
  if (!evidence) return null;
  return (
    <path
      d={path}
      fill="none"
      stroke="#ffffff"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={5}
      opacity={0.9}
      pointerEvents="none"
    />
  );
}

export function EdgeEndpointSockets({
  sourceX,
  sourceY,
  targetX,
  targetY,
  stroke,
  evidence,
  active,
}: EndpointSocketProps) {
  if (!evidence) return null;
  const r = active ? 4.5 : 3.5;
  return (
    <g pointerEvents="none">
      <circle cx={sourceX} cy={sourceY} r={r + 2} fill="#ffffff" opacity={0.95} />
      <circle cx={targetX} cy={targetY} r={r + 2} fill="#ffffff" opacity={0.95} />
      <circle cx={sourceX} cy={sourceY} r={r} fill="#ffffff" stroke={stroke} strokeWidth={2} />
      <circle cx={targetX} cy={targetY} r={r} fill="#ffffff" stroke={stroke} strokeWidth={2} />
    </g>
  );
}
