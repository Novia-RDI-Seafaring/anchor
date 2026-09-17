import { CONNECT_TOOL } from "./registry";

/**
 * One letter per tool, the way every drawing tool does it: press it and the
 * tool is armed. The toolbar prints each letter on its tile, so the shortcut
 * is discovered by using the toolbar rather than by reading documentation.
 *
 * Kept in its own module so the toolbar and its tests share one source, and
 * so the mapping can be asserted without mounting the toolbar.
 */
export const TOOL_KEYS: Record<string, string> = {
  r: "concept",
  o: "entity",
  d: "funnel",
  f: "area",
  t: "text",
  n: "note",
  m: "markdown",
  a: CONNECT_TOOL,
  c: CONNECT_TOOL,
};

/** The letter shown on a tool's tile. First key wins when two map to one tool. */
export const KEY_FOR_TOOL: Record<string, string> = Object.entries(TOOL_KEYS).reduce(
  (acc, [key, tool]) => (acc[tool] ? acc : { ...acc, [tool]: key.toUpperCase() }),
  {} as Record<string, string>,
);
