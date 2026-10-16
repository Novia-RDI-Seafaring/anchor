import { describe, expect, it } from "vitest";

import { sectionHint } from "./SectionPrimitive";

describe("section hint", () => {
  it("names the kind and the page", () => {
    expect(sectionHint("table", 3)).toBe("table · p. 3");
  });

  it("reads a compound kind as words", () => {
    expect(sectionHint("key_value_list", 2)).toBe("key value list · p. 2");
  });

  it("falls back to section without a kind", () => {
    expect(sectionHint(undefined, undefined)).toBe("section");
  });
});
