import { describe, expect, it } from "vitest";

import { CONNECT_TOOL } from "./registry";
import { KEY_FOR_TOOL, TOOL_KEYS } from "./toolKeys";

describe("tool shortcuts", () => {
  it("maps a letter to each drawing tool", () => {
    expect(TOOL_KEYS.t).toBe("text");
    expect(TOOL_KEYS.r).toBe("concept");
    expect(TOOL_KEYS.a).toBe(CONNECT_TOOL);
  });

  it("gives every tool one letter to print on its tile", () => {
    expect(KEY_FOR_TOOL.text).toBe("T");
    expect(KEY_FOR_TOOL.concept).toBe("R");
    // Two keys reach the connector; the tile shows the first.
    expect(KEY_FOR_TOOL[CONNECT_TOOL]).toBe("A");
  });
});
