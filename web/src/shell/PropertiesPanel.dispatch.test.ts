/**
 * PropertiesPanel.dispatch unit tests.
 *
 * Pins the dispatcher's contract:
 *   - known fact/note → MarkdownEditor
 *   - known spec      → SpecEditor
 *   - known shapes    → LabelEditor
 *   - known document  → DocumentReadonly
 *   - anything else   → JsonEscapeHatch  (open-ended plugin types fall here)
 */
import { describe, expect, it } from "vitest";

import {
  DocumentReadonly,
  JsonEscapeHatch,
  LabelEditor,
  MarkdownEditor,
  SpecEditor,
  dispatchEditor,
} from "./PropertiesPanel.dispatch";

describe("dispatchEditor", () => {
  it("returns MarkdownEditor for fact", () => {
    expect(dispatchEditor("fact")).toBe(MarkdownEditor);
  });

  it("returns MarkdownEditor for note", () => {
    expect(dispatchEditor("note")).toBe(MarkdownEditor);
  });

  it("returns SpecEditor for spec", () => {
    expect(dispatchEditor("spec")).toBe(SpecEditor);
  });

  it("returns DocumentReadonly for document", () => {
    expect(dispatchEditor("document")).toBe(DocumentReadonly);
  });

  it.each(["concept", "entity", "funnel", "area"])(
    "returns LabelEditor for shape %s",
    (kind) => {
      expect(dispatchEditor(kind)).toBe(LabelEditor);
    },
  );

  it("returns JsonEscapeHatch for unknown node types", () => {
    expect(dispatchEditor("model3d")).toBe(JsonEscapeHatch);
    expect(dispatchEditor("cad:model")).toBe(JsonEscapeHatch);
    expect(dispatchEditor("sysml:block")).toBe(JsonEscapeHatch);
    expect(dispatchEditor("plugin:future-thing")).toBe(JsonEscapeHatch);
  });

  it("returns JsonEscapeHatch for undefined / empty", () => {
    expect(dispatchEditor(undefined)).toBe(JsonEscapeHatch);
    expect(dispatchEditor("")).toBe(JsonEscapeHatch);
  });
});
