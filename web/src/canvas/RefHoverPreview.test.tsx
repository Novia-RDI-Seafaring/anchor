import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { expand, insetWithin, RefHoverPreview } from "@/canvas/RefHoverPreview";

const REF = { slug: "lkh", page: 2, bbox: [100, 200, 160, 220] };

function rect(partial: Partial<DOMRect>): DOMRect {
  return { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0,
    toJSON: () => ({}), ...partial } as DOMRect;
}

describe("crop geometry", () => {
  it("keeps page around the referenced box so you can see where it came from", () => {
    const box = expand([100, 200, 160, 220], 50);
    expect(box).toEqual({ left: 50, top: 150, right: 210, bottom: 270 });
  });

  it("clamps at the page origin rather than going negative", () => {
    const box = expand([10, 5, 40, 30], 50);
    expect(box.left).toBe(0);
    expect(box.top).toBe(0);
  });

  it("places the referenced box inside the crop as percentages", () => {
    const crop = { left: 0, top: 0, right: 200, bottom: 100 };
    expect(insetWithin([50, 25, 150, 75], crop)).toEqual({
      left: "25%", top: "25%", width: "50%", height: "50%",
    });
  });

  it("clamps an inset that runs outside the crop", () => {
    const crop = { left: 0, top: 0, right: 100, bottom: 100 };
    const inset = insetWithin([-50, -50, 150, 150], crop)!;
    expect(inset.left).toBe("0%");
    expect(inset.top).toBe("0%");
    expect(inset.width).toBe("100%");
  });

  it("returns nothing for a degenerate crop rather than dividing by zero", () => {
    expect(insetWithin([0, 0, 10, 10], { left: 5, top: 5, right: 5, bottom: 5 })).toBeNull();
  });
});

describe("RefHoverPreview", () => {
  it("shows a crop of the page with the referenced part boxed", () => {
    render(<RefHoverPreview refValue={REF} anchorRect={rect({ left: 100, right: 200, top: 100 })} />);
    const img = screen.getByTestId("ref-hover-crop") as HTMLImageElement;
    // Cropped around the ref, not the whole page.
    expect(img.src).toContain("/pages/2/crop");
    expect(img.src).toContain("bbox=");
    expect(screen.getByTestId("ref-hover-box")).toBeTruthy();
  });

  it("opens to the right of the link when there is room", () => {
    render(<RefHoverPreview refValue={REF} anchorRect={rect({ left: 100, right: 200, top: 100 })} />);
    const panel = screen.getByTestId("ref-hover-preview");
    expect(parseInt(panel.style.left, 10)).toBeGreaterThan(200);
  });

  it("flips to the left when the panel would overflow the window", () => {
    const nearEdge = window.innerWidth - 40;
    render(
      <RefHoverPreview
        refValue={REF}
        anchorRect={rect({ left: nearEdge - 60, right: nearEdge, top: 100 })}
      />,
    );
    const panel = screen.getByTestId("ref-hover-preview");
    expect(parseInt(panel.style.left, 10)).toBeLessThan(nearEdge - 60);
  });

  it("stays on screen vertically for a link near the bottom", () => {
    render(
      <RefHoverPreview
        refValue={REF}
        anchorRect={rect({ left: 100, right: 200, top: window.innerHeight - 5 })}
      />,
    );
    const panel = screen.getByTestId("ref-hover-preview");
    expect(parseInt(panel.style.top, 10)).toBeLessThan(window.innerHeight);
    expect(parseInt(panel.style.top, 10)).toBeGreaterThanOrEqual(0);
  });

  it("renders nothing when the ref has no page or box to show", () => {
    const { container } = render(
      <RefHoverPreview refValue={{ slug: "lkh" }} anchorRect={rect({ left: 0, right: 10, top: 0 })} />,
    );
    expect(container.textContent).toBe("");
  });

  it("names the document and page so the panel stands on its own", () => {
    render(<RefHoverPreview refValue={REF} anchorRect={rect({ left: 100, right: 200, top: 100 })} />);
    expect(screen.getByTestId("ref-hover-preview").textContent).toContain("page 2");
  });
});
