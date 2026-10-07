import type { Box } from "../../intent-overlay";
export type { MarkupModel } from "../../intent-overlay/types";
export type MarkupProps = {
  active: boolean;
  boxes: Box[];
  workspaceSlug: string;
  onFiled?: () => void;
  onExit?: () => void;
};
