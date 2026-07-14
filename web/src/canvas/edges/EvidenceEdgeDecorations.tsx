type EndpointSocketProps = {
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  stroke: string;
  evidence: boolean;
  active: boolean;
};

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
  const radius = active ? 4.5 : 3.5;
  return (
    <g pointerEvents="none">
      <circle cx={sourceX} cy={sourceY} r={radius + 2} fill="#ffffff" opacity={0.95} />
      <circle cx={targetX} cy={targetY} r={radius + 2} fill="#ffffff" opacity={0.95} />
      <circle cx={sourceX} cy={sourceY} r={radius} fill="#ffffff" stroke={stroke} strokeWidth={2} />
      <circle cx={targetX} cy={targetY} r={radius} fill="#ffffff" stroke={stroke} strokeWidth={2} />
    </g>
  );
}
