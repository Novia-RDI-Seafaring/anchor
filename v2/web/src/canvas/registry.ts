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
 * Built-in shapes (`concept`, `entity`, `fact`, `area`, `note`) are
 * structural, not OIP primitives — they're canvas-internal node types
 * registered by name and rendered by their own component.
 */
import type { ComponentType } from "react";
import type { NodeProps, NodeTypes } from "@xyflow/react";

// Primitives — generic OIP-aware renderers
import { DocumentPrimitive } from "./primitives/DocumentPrimitive";
import { TablePrimitive } from "./primitives/TablePrimitive";

// Shapes — canvas-internal structural node types
import { AreaNode } from "./shapes/AreaNode";
import { ConceptNode } from "./shapes/ConceptNode";
import { EntityNode } from "./shapes/EntityNode";
import { FactNode } from "./shapes/FactNode";
import { NoteNode } from "./shapes/NoteNode";

const registry = new Map<string, ComponentType<NodeProps>>();

export function registerNodeRenderer(
  name: string,
  component: ComponentType<NodeProps>,
): void {
  if (registry.has(name)) {
    // Last-writer-wins so plugins can override defaults; warn for visibility.
    // eslint-disable-next-line no-console
    console.warn(`registerNodeRenderer: overriding existing renderer for '${name}'`);
  }
  registry.set(name, component);
}

export function unregisterNodeRenderer(name: string): void {
  registry.delete(name);
}

export function getNodeRenderer(name: string): ComponentType<NodeProps> | undefined {
  return registry.get(name);
}

export function nodeTypeNames(): string[] {
  return [...registry.keys()].sort();
}

// Built-in defaults — registered against canonical node_type strings.
// Producers that map their region kinds to one of these primitives via
// `ui_hints.node_types[].renders = "primitive:<name>"` get rendering for free.
registerNodeRenderer("concept", ConceptNode);
registerNodeRenderer("entity", EntityNode);
registerNodeRenderer("fact", FactNode);
registerNodeRenderer("area", AreaNode);
registerNodeRenderer("note", NoteNode);

// Primitives — OIP-aware
registerNodeRenderer("document", DocumentPrimitive);
registerNodeRenderer("spec", TablePrimitive);
// future primitives (when their renderers land):
//   registerNodeRenderer("media", MediaPrimitive);
//   registerNodeRenderer("model3d", Model3DPrimitive);
//   registerNodeRenderer("code", CodePrimitive);
//   registerNodeRenderer("plot", PlotPrimitive);
//   registerNodeRenderer("image", ImagePrimitive);

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
