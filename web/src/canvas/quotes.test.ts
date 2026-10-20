import { describe, expect, it } from "vitest";

import { parseAnchorHref, formatAnchorHref } from "./anchorHref";
import { boxesOnPage, formatQuote, quoteBoxes, quoteParams, quoteProblem } from "./quotes";

describe("quotes", () => {
  it("writes the text-fragment grammar", () => {
    expect(formatQuote({ exact: "EPDM" })).toBe("EPDM");
    expect(formatQuote({ exact: "EPDM", prefix: "+140 °C (", suffix: ")" })).toBe("+140 °C (-,EPDM,-)");
  });

  it("asks the server only for quotes not yet placed", () => {
    const quotes = [
      "EPDM",
      { exact: "+140", boxes: [[1, 2, 3, 4]] },
      { exact: "6 bar", prefix: "max" },
    ];
    expect(quoteParams(quotes)).toEqual(["EPDM", "max-,6 bar"]);
  });

  it("draws saved and newly placed boxes on their pages", () => {
    const places = quoteBoxes(
      [{ exact: "+140", boxes: [[1, 2, 3, 4]] }],
      2,
      [{ exact: "F", page: 3, boxes: [[5, 6, 7, 8]] }, { exact: "x", problem: "not_found" }],
    );
    expect(boxesOnPage(places, 2)).toEqual([[1, 2, 3, 4]]);
    expect(boxesOnPage(places, 3)).toEqual([[5, 6, 7, 8]]);
  });

  it("says which quoted words could not be lit", () => {
    expect(quoteProblem([{ exact: "EPDM", problem: "ambiguous" }])).toContain("more than once");
    expect(quoteProblem([{ exact: "+140", boxes: [[1, 2, 3, 4]] }])).toBeNull();
  });

  it("reads and writes quotes in anchor links", () => {
    const ref = parseAnchorHref("anchor:px?page=2&item=p2-i14&quote=EPDM&quote=%2B140%20%C2%B0C%20(-,EPDM,-)");
    expect(ref?.quotes).toEqual(["EPDM", "+140 °C (-,EPDM,-)"]);
    expect(parseAnchorHref(formatAnchorHref(ref!))?.quotes).toEqual(ref?.quotes);
  });
});
