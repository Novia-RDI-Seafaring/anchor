import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PictureHighlightBoxes } from "./PictureHighlights";

describe("PictureHighlightBoxes", () => {
  it("keeps each placement's mark when the hovered reference changes", () => {
    const { rerender } = render(<PictureHighlightBoxes boxes={[
      { key: "main", left: 10, top: 20, width: 30, height: 5 },
      { key: "also-0", left: 50, top: 60, width: 4, height: 5 },
    ]} />);
    const before = screen.getAllByTestId("image-source-highlight");
    rerender(<PictureHighlightBoxes boxes={[
      { key: "main", left: 12, top: 30, width: 25, height: 6 },
      { key: "also-0", left: 55, top: 70, width: 5, height: 6 },
    ]} />);
    const after = screen.getAllByTestId("image-source-highlight");
    after.forEach((mark, i) => {
      expect(mark).toBe(before[i]);
      expect(mark.classList.contains("anchor-mark")).toBe(true);
      expect(mark.classList.contains("anchor-mark-flying")).toBe(true);
      expect(mark.classList.contains("anchor-mark-fade")).toBe(true);
    });
    expect(after[0]!.style.left).toBe("12%");
    expect(after[1]!.style.top).toBe("70%");
  });
});
