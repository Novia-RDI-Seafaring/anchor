import { IntentOverlay } from "../intent-overlay";
import { useAnchorOverlayHost } from "./markup/AnchorHost";
import type { MarkupProps } from "./markup/types";

export function CommentLasso({ boxes, workspaceSlug, ...props }: MarkupProps) {
  const host = useAnchorOverlayHost(workspaceSlug, boxes);
  return <IntentOverlay {...props} host={host} />;
}
