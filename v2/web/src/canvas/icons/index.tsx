/**
 * Canvas pictogram set.
 *
 * Small, stroke-based SVG icons reused across primitives and shapes. Any
 * node renderer can opt into rendering one as a leading glyph by reading
 * `data.pictogram: "<name>"` and passing it to <Pictogram>.
 *
 * Add new icons here, not in node files. Keep them ~24px square, single
 * stroke, currentColor — that way they pick up the parent's text colour
 * and invert cleanly when the canvas is rendered white-on-black.
 */
import type { ComponentType, ReactElement, SVGProps } from "react";

const STROKE: SVGProps<SVGSVGElement> = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

const PageIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...STROKE} {...p}>
    <path d="M6 3h8l4 4v14H6z" />
    <path d="M14 3v4h4" />
    <path d="M9 12h6M9 15h6M9 18h4" />
  </svg>
);

const ModelIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...STROKE} {...p}>
    <rect x="3" y="9" width="6" height="6" rx="1" />
    <rect x="15" y="9" width="6" height="6" rx="1" />
    <path d="M9 12h6" />
    <path d="M13 10l2 2-2 2" />
  </svg>
);

const CubeIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...STROKE} {...p}>
    <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" />
    <path d="M4 7.5L12 12l8-4.5" />
    <path d="M12 12v9" />
  </svg>
);

const PanelIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...STROKE} {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <circle cx="8" cy="11" r="1.2" />
    <circle cx="16" cy="11" r="1.2" />
    <circle cx="12" cy="16" r="1.2" />
    <path d="M8 11l4 5M16 11l-4 5" />
  </svg>
);

const ChatIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...STROKE} {...p}>
    <path d="M4 6h16v10H8l-4 4z" />
  </svg>
);

const MicIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...STROKE} {...p}>
    <rect x="9" y="3" width="6" height="12" rx="3" />
    <path d="M5 11a7 7 0 0014 0" />
    <path d="M12 18v3" />
  </svg>
);

const HeadsetIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...STROKE} {...p}>
    <path d="M3 13a9 9 0 0118 0v4a2 2 0 01-2 2h-3v-6h5" />
    <path d="M5 13v6h3v-6H3" />
  </svg>
);

const ChartIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...STROKE} {...p}>
    <path d="M4 19h16" />
    <path d="M6 16l4-4 3 3 5-7" />
  </svg>
);

const HexagonIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...STROKE} {...p}>
    <path d="M12 3l7.5 4.5v9L12 21l-7.5-4.5v-9z" />
  </svg>
);

const WaveIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...STROKE} {...p}>
    <path d="M3 12c2-4 4-4 6 0s4 4 6 0 4-4 6 0" />
  </svg>
);

const FunnelIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...STROKE} {...p}>
    <path d="M3 5h18l-7 8v6l-4 2v-8z" />
  </svg>
);

const StackIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...STROKE} {...p}>
    <path d="M5 6h12v3H5zM5 11h12v3H5zM5 16h12v3H5z" />
  </svg>
);

const GraphIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...STROKE} {...p}>
    <circle cx="6" cy="6" r="2" />
    <circle cx="18" cy="6" r="2" />
    <circle cx="12" cy="18" r="2" />
    <path d="M6 6l12 0M6 6l6 12M18 6l-6 12" />
  </svg>
);

const ICONS: Record<string, ComponentType<SVGProps<SVGSVGElement>>> = {
  page: PageIcon,
  model: ModelIcon,
  cube: CubeIcon,
  panel: PanelIcon,
  chat: ChatIcon,
  mic: MicIcon,
  headset: HeadsetIcon,
  chart: ChartIcon,
  hexagon: HexagonIcon,
  wave: WaveIcon,
  funnel: FunnelIcon,
  stack: StackIcon,
  graph: GraphIcon,
};

export type PictogramName = keyof typeof ICONS | string;

export function Pictogram({
  name,
  size = 18,
  className = "",
  ...rest
}: { name: PictogramName | undefined; size?: number; className?: string } & SVGProps<SVGSVGElement>): ReactElement | null {
  if (!name) return null;
  const Icon = ICONS[name];
  if (!Icon) return null;
  return <Icon width={size} height={size} className={className} {...rest} />;
}

export function pictogramNames(): string[] {
  return Object.keys(ICONS).sort();
}
