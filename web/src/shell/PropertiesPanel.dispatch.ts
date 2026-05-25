/**
 * PropertiesPanel dispatch — maps `node_type` to the editor component.
 *
 * Kept as a tiny pure function (no React, no DOM) so it's trivially
 * unit-testable from `PropertiesPanel.dispatch.test.ts`. Unknown node
 * types fall back to `JsonEscapeHatch` so the panel always renders
 * something useful, even for plugins it doesn't know about.
 *
 * Mapping rules (kept in sync with the canvas registry):
 *   - shapes (concept / entity / funnel / area)  → LabelEditor
 *   - cards (fact / note)                        → MarkdownEditor
 *   - producers/spec                             → SpecEditor
 *   - producers/document                         → DocumentReadonly
 *   - everything else                            → JsonEscapeHatch
 */
import type { ComponentType } from "react";

import { DocumentReadonly } from "./editors/DocumentReadonly";
import { JsonEscapeHatch } from "./editors/JsonEscapeHatch";
import { LabelEditor } from "./editors/LabelEditor";
import { MarkdownEditor } from "./editors/MarkdownEditor";
import { SpecEditor } from "./editors/SpecEditor";
import type { EditorProps } from "./editors/_types";

type EditorComponent = ComponentType<EditorProps>;

const SHAPE_TYPES = new Set<string>(["concept", "entity", "funnel", "area"]);
const CARD_TYPES = new Set<string>(["fact", "note"]);

export function dispatchEditor(nodeType: string | undefined): EditorComponent {
  if (!nodeType) return JsonEscapeHatch;
  if (SHAPE_TYPES.has(nodeType)) return LabelEditor;
  if (CARD_TYPES.has(nodeType)) return MarkdownEditor;
  if (nodeType === "spec") return SpecEditor;
  if (nodeType === "document") return DocumentReadonly;
  return JsonEscapeHatch;
}

// Re-export named editors for the unit test to assert identity equality.
export { DocumentReadonly, JsonEscapeHatch, LabelEditor, MarkdownEditor, SpecEditor };
