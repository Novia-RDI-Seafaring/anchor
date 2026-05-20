/**
 * Canvas node-type registry + render dispatcher.
 *
 * Three render paths the canvas supports per OIP `ui_hints.renders`:
 *
 *   1. `primitive:<name>` (e.g. `primitive:document`)
 *      → built-in React component, ships with the canvas, generic across
 *        producers using a conventional source_ref kind.
 *
 *   2. `extension-component`
 *      → producer ships its own Web Component (Lit / Stencil / vanilla);
 *        canvas lazy-loads the module from `module_url` and renders the
 *        declared custom element. Stubbed today — wire up when the first
 *        external producer needs it.
 *
 *   3. `a2ui`
 *      → producer's region carries an A2UI message (Google's UI protocol);
 *        canvas hosts a built-in A2UI renderer. Stubbed today — wire up
 *        when we install `@a2ui/lit`.
 *
 * The Python core uses an open `NodeTypeRegistry` (see
 * `core/workspace/node_types.py`); this is its UI-side counterpart.
 *
 * Built-in shapes (`concept`, `entity`, `fact`, `area`, `note`, `funnel`)
 * are structural, not OIP primitives — they're canvas-internal node types
 * registered by name and rendered by their own component.
 *
 * Each registered renderer can carry optional palette metadata describing
 * how the floating top toolbar should advertise the node type (group,
 * display label, drag-out defaults). The metadata is the registry's own
 * concern; node renderers never read it themselves. This is what lets the
 * toolbar "loaded dynamically from the registry — don't hardcode" instead
 * of maintaining a parallel list of producers.
 */
import type { ComponentType } from "react";
import type { NodeProps, NodeTypes } from "@xyflow/react";

// Primitives — generic OIP-aware renderers
import { DocumentPrimitive } from "./primitives/DocumentPrimitive";
import { Model3DPrimitive } from "./primitives/Model3DPrimitive";
import { SubCanvasPrimitive } from "./primitives/SubCanvasPrimitive";
import { SysmlBlockPrimitive } from "./primitives/SysmlBlockPrimitive";
import { SysmlPackagePrimitive } from "./primitives/SysmlPackagePrimitive";
import { SysmlRequirementPrimitive } from "./primitives/SysmlRequirementPrimitive";
import { TablePrimitive } from "./primitives/TablePrimitive";

// Shapes — canvas-internal structural node types
import { AreaNode } from "./shapes/AreaNode";
import { ConceptNode } from "./shapes/ConceptNode";
import { EntityNode } from "./shapes/EntityNode";
import { FactNode } from "./shapes/FactNode";
import { FunnelNode } from "./shapes/FunnelNode";
import { NoteNode } from "./shapes/NoteNode";

/** Optional toolbar/palette metadata for a registered node type. */
export type PaletteMeta = {
  /** Section in the toolbar. */
  group: "shapes" | "cards" | "producers";
  /** Human-readable label (tooltip + accessibility). */
  label: string;
  /** Single-line description used in the tooltip subtitle. */
  hint?: string;
  /** Initial node width if the drag-out should seed one (e.g. area). */
  width?: number;
  /** Initial node height (e.g. area). */
  height?: number;
  /** Extra `data` to merge into the dropped node. */
  data?: Record<string, unknown>;
  /**
   * If true, the toolbar drops the node with `label: ""` so the user can
   * immediately rename inline. Pure shapes opt in; cards keep their label.
   */
  noDefaultLabel?: boolean;
  /** Glyph identifier for the toolbar icon (matches the tile's SVG). */
  glyph: "rect" | "circle" | "diamond" | "dashed-rect" | "note" | "fact" | "page" | "table" | "cube" | "block" | "requirement" | "package" | "fmu" | "sub-canvas";
  /** Ordering hint within a section (lower first). */
  order?: number;
  /**
   * When false the toolbar suppresses the entry. Producers that only ever
   * land via the Library drawer (`document`, `cad:model`, ...) opt out
   * here so the toolbar advertises the *concept* without trying to drop a
   * stub node that has no source content yet.
   */
  toolbar?: boolean;
};

const registry = new Map<string, ComponentType<NodeProps>>();
const paletteMeta = new Map<string, PaletteMeta>();

export function registerNodeRenderer(
  name: string,
  component: ComponentType<NodeProps>,
  meta?: PaletteMeta,
): void {
  if (registry.has(name)) {
    // Last-writer-wins so plugins can override defaults; warn for visibility.
    // eslint-disable-next-line no-console
    console.warn(`registerNodeRenderer: overriding existing renderer for '${name}'`);
  }
  registry.set(name, component);
  if (meta) paletteMeta.set(name, meta);
}

export function unregisterNodeRenderer(name: string): void {
  registry.delete(name);
  paletteMeta.delete(name);
}

export function getNodeRenderer(name: string): ComponentType<NodeProps> | undefined {
  return registry.get(name);
}

export function nodeTypeNames(): string[] {
  return [...registry.keys()].sort();
}

/** All registered palette entries, grouped and ordered for toolbar consumption. */
export function paletteEntries(group: PaletteMeta["group"]): Array<{ name: string; meta: PaletteMeta }> {
  const entries: Array<{ name: string; meta: PaletteMeta }> = [];
  for (const [name, meta] of paletteMeta) {
    if (meta.group !== group) continue;
    if (meta.toolbar === false) continue;
    entries.push({ name, meta });
  }
  entries.sort((a, b) => (a.meta.order ?? 100) - (b.meta.order ?? 100));
  return entries;
}

/**
 * True when a node type can usefully be dragged out of the toolbar to
 * create a node from scratch — i.e. shapes and cards. Producers carry
 * external content references and must be added via the Library drawer.
 *
 * Exception: `canvas` (sub-canvas link) is a producer but is dragged out
 * directly because its "content" is just another workspace we provision
 * server-side on drop. See `LeftToolRail`'s producer-section + the
 * `__create_sub_canvas` payload flag handled in `CanvasGraph.onDrop`.
 */
export function canDragFromToolbar(name: string): boolean {
  const meta = paletteMeta.get(name);
  if (!meta) return false;
  if (meta.group === "shapes" || meta.group === "cards") return true;
  return name === "canvas";
}

// Built-in defaults — registered against canonical node_type strings.
// Producers that map their region kinds to one of these primitives via
// `ui_hints.node_types[].renders = "primitive:<name>"` get rendering for free.
registerNodeRenderer("concept", ConceptNode, {
  group: "shapes",
  label: "Rectangle",
  hint: "rounded rectangle",
  glyph: "rect",
  noDefaultLabel: true,
  order: 10,
});
registerNodeRenderer("entity", EntityNode, {
  group: "shapes",
  label: "Circle",
  hint: "circular shape",
  glyph: "circle",
  noDefaultLabel: true,
  order: 20,
});
registerNodeRenderer("funnel", FunnelNode, {
  group: "shapes",
  label: "Diamond",
  hint: "diamond shape",
  glyph: "diamond",
  noDefaultLabel: true,
  order: 30,
});
registerNodeRenderer("area", AreaNode, {
  group: "shapes",
  label: "Container",
  hint: "dashed container",
  glyph: "dashed-rect",
  noDefaultLabel: true,
  width: 360,
  height: 220,
  order: 40,
});

registerNodeRenderer("fact", FactNode, {
  group: "cards",
  label: "Fact",
  hint: "single assertion",
  glyph: "fact",
  order: 10,
});
registerNodeRenderer("note", NoteNode, {
  group: "cards",
  label: "Note",
  hint: "free-form sticky note",
  glyph: "note",
  order: 20,
});

// Primitives — OIP-aware. Producers register against canonical node_type
// strings; the registry's palette metadata is what surfaces them to the
// toolbar's Producers section. These entries are *informational* — every
// producer requires real content (a document slug, a CAD slug, a SysML
// model) to make a useful node, so the toolbar shows them as icons with
// a tooltip and routes clicks to the Library drawer instead of dropping
// stub nodes.
registerNodeRenderer("document", DocumentPrimitive, {
  group: "producers",
  label: "Document",
  hint: "ingested PDFs · open Library",
  glyph: "page",
  order: 10,
});
registerNodeRenderer("spec", TablePrimitive, {
  group: "producers",
  label: "Spec table",
  hint: "drag rows out of a document",
  glyph: "table",
  order: 20,
});
// Sub-canvas — link to another workspace. Drop-creates a sibling canvas
// behind the scenes (see LeftToolRail) so the linking node is always
// pointing at an extant child. Double-clicking drills in.
registerNodeRenderer("canvas", SubCanvasPrimitive, {
  group: "producers",
  label: "Sub-canvas",
  hint: "link to another canvas · drill in by double-click",
  glyph: "sub-canvas",
  order: 5,
  noDefaultLabel: false,
});
registerNodeRenderer("model3d", Model3DPrimitive, {
  group: "producers",
  label: "Model3D",
  hint: "3D model viewport",
  glyph: "cube",
  order: 30,
});
registerNodeRenderer("cad:model", Model3DPrimitive, {
  group: "producers",
  label: "CAD model",
  hint: "anchor_cad · open Library",
  glyph: "cube",
  order: 40,
});

// SysML v2 primitives — anchor_sysml extension's manifest node_types
registerNodeRenderer("sysml:block", SysmlBlockPrimitive, {
  group: "producers",
  label: "SysML block",
  hint: "block definition / usage",
  glyph: "block",
  order: 50,
});
registerNodeRenderer("sysml:requirement", SysmlRequirementPrimitive, {
  group: "producers",
  label: "SysML requirement",
  hint: "requirement",
  glyph: "requirement",
  order: 60,
});
registerNodeRenderer("sysml:package", SysmlPackagePrimitive, {
  group: "producers",
  label: "SysML package",
  hint: "package container",
  glyph: "package",
  order: 70,
});
// future primitives (when their renderers land):
//   registerNodeRenderer("media", MediaPrimitive);
//   registerNodeRenderer("code", CodePrimitive);
//   registerNodeRenderer("plot", PlotPrimitive);
//   registerNodeRenderer("image", ImagePrimitive);
//   registerNodeRenderer("fmu", FmuPrimitive);

/**
 * Lazy-load a Web Component module and register the resulting custom
 * element under a node_type. Stub today: wire up when the first external
 * producer ships a `renders: "extension-component"` manifest.
 */
export async function registerExtensionComponent(
  nodeType: string,
  moduleUrl: string,
  customElementTag: string,
): Promise<void> {
  // eslint-disable-next-line no-console
  console.warn(
    `registerExtensionComponent: stub — module=${moduleUrl}, tag=${customElementTag}, type=${nodeType}`,
  );
  // Future implementation:
  //   await import(/* @vite-ignore */ moduleUrl);
  //   if (!customElements.get(customElementTag)) {
  //     console.error(`module ${moduleUrl} did not register <${customElementTag}>`);
  //     return;
  //   }
  //   registerNodeRenderer(nodeType, makeWebComponentWrapper(customElementTag));
}

/**
 * Render an A2UI message inside a node body. Stub today: wire up when
 * `@a2ui/lit` is installed and one of our producers actually emits A2UI.
 */
export function renderA2UIFragment(_a2uiMessage: unknown): null {
  // eslint-disable-next-line no-console
  console.warn("renderA2UIFragment: stub — A2UI renderer not yet wired");
  return null;
}

/**
 * The proxy ReactFlow consumes. ReactFlow asks for `nodeTypes[name]`;
 * we serve from the registry without recompilation.
 */
export const nodeTypes: NodeTypes = new Proxy({} as NodeTypes, {
  get(_target, prop: string) {
    return registry.get(prop);
  },
  has(_target, prop: string) {
    return registry.has(prop);
  },
  ownKeys() {
    return [...registry.keys()];
  },
  getOwnPropertyDescriptor(_target, prop: string) {
    if (registry.has(prop)) {
      return { enumerable: true, configurable: true, value: registry.get(prop) };
    }
    return undefined;
  },
});
