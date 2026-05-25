/**
 * colors.ts unit tests — pin the resolveColors contract:
 *
 *   - Missing data / missing fields → defaults (DEFAULT_BG, DEFAULT_STROKE).
 *   - Valid string overrides → echoed back.
 *   - Invalid input (number, empty string, null, undefined) → fall through
 *     to the default without throwing. The Style picker can therefore feed
 *     us anything the user dropped in and we don't blow up the renderer.
 */
import { describe, expect, it } from "vitest";

import { DEFAULT_BG, DEFAULT_STROKE, resolveColors, resolveText } from "./colors";

describe("resolveColors", () => {
  it("returns defaults when data is undefined", () => {
    expect(resolveColors(undefined)).toEqual({ bg: DEFAULT_BG, stroke: DEFAULT_STROKE });
  });

  it("returns defaults when data is null", () => {
    expect(resolveColors(null)).toEqual({ bg: DEFAULT_BG, stroke: DEFAULT_STROKE });
  });

  it("returns defaults when data is an empty object", () => {
    expect(resolveColors({})).toEqual({ bg: DEFAULT_BG, stroke: DEFAULT_STROKE });
  });

  it("returns defaults when fields are missing", () => {
    expect(resolveColors({ label: "ignored" })).toEqual({
      bg: DEFAULT_BG,
      stroke: DEFAULT_STROKE,
    });
  });

  it("honours bg_color override (hex)", () => {
    const { bg } = resolveColors({ bg_color: "#fef3c7" });
    expect(bg).toBe("#fef3c7");
  });

  it("honours stroke_color override (rgb)", () => {
    const { stroke } = resolveColors({ stroke_color: "rgb(2, 132, 199)" });
    expect(stroke).toBe("rgb(2, 132, 199)");
  });

  it("honours both overrides together", () => {
    expect(resolveColors({ bg_color: "#fff", stroke_color: "black" })).toEqual({
      bg: "#fff",
      stroke: "black",
    });
  });

  it("falls through to default on empty string", () => {
    expect(resolveColors({ bg_color: "", stroke_color: "   " })).toEqual({
      bg: DEFAULT_BG,
      stroke: DEFAULT_STROKE,
    });
  });

  it("falls through to default on non-string input", () => {
    // Callers should never pass these, but the helper is a render-path
    // guardrail so it must survive bad data without throwing.
    expect(
      resolveColors({ bg_color: 42 as unknown as string, stroke_color: null as unknown as string }),
    ).toEqual({ bg: DEFAULT_BG, stroke: DEFAULT_STROKE });
  });

  it("trims surrounding whitespace from a valid value", () => {
    expect(resolveColors({ bg_color: "  #abc  " })).toEqual({
      bg: "#abc",
      stroke: DEFAULT_STROKE,
    });
  });
});

describe("resolveText", () => {
  it("returns defaults when data is empty", () => {
    const t = resolveText({});
    expect(t.color).toBe(DEFAULT_STROKE);
    expect(t.fontWeight).toBe(400);
    expect(t.textAlign).toBe("left");
    expect(t.fontFamily).toBe("inherit");
    expect(t.fontSize).toBe("0.875rem");
  });

  it("falls through stroke_color when text_color is unset", () => {
    const t = resolveText({ stroke_color: "rgb(2, 132, 199)" });
    expect(t.color).toBe("rgb(2, 132, 199)");
  });

  it("prefers text_color over stroke_color", () => {
    const t = resolveText({ text_color: "#ff0000", stroke_color: "#00ff00" });
    expect(t.color).toBe("#ff0000");
  });

  it("toggles fontWeight via text_bold", () => {
    expect(resolveText({ text_bold: true }).fontWeight).toBe(700);
    expect(resolveText({ text_bold: false }).fontWeight).toBe(400);
  });

  it("honours valid text_align values", () => {
    expect(resolveText({ text_align: "center" }).textAlign).toBe("center");
    expect(resolveText({ text_align: "right" }).textAlign).toBe("right");
    expect(resolveText({ text_align: "left" }).textAlign).toBe("left");
  });

  it("falls back to left on invalid text_align", () => {
    expect(resolveText({ text_align: "wibble" as unknown as "left" }).textAlign).toBe("left");
  });

  it("maps text_size to rems", () => {
    expect(resolveText({ text_size: "sm" }).fontSize).toBe("0.75rem");
    expect(resolveText({ text_size: "md" }).fontSize).toBe("0.875rem");
    expect(resolveText({ text_size: "lg" }).fontSize).toBe("1rem");
  });

  it("maps text_family to font stacks", () => {
    expect(resolveText({ text_family: "default" }).fontFamily).toBe("inherit");
    expect(resolveText({ text_family: "sans" }).fontFamily).toMatch(/sans-serif/);
    expect(resolveText({ text_family: "serif" }).fontFamily).toMatch(/serif/);
    expect(resolveText({ text_family: "mono" }).fontFamily).toMatch(/monospace/);
  });
});
