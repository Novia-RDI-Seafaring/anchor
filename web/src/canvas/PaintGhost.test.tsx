/**
 * PaintGhost tests — pin the WYSIWYG drop math and the basic outline
 * dispatch.
 *
 * Why this matters: the ghost rect (screen coords) and the dropped node's
 * flow rect must round-trip through `screenToFlowPosition` consistently.
 * Bugs here surface as "the drawn rectangle is in one place, the dropped
 * node lands in another" — exactly the user-reported regression these
 * tests were written to prevent.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  PaintGhost,
  ghostIsSquare,
  ghostOutlineKind,
  maybeSquareRect,
  paintRectFrom,
} from "./PaintGhost";

describe("paintRectFrom", () => {
  it("normalises the rect when current is bottom-right of down", () => {
    const r = paintRectFrom({ x: 400, y: 300 }, { x: 600, y: 500 });
    expect(r).toEqual({ left: 400, top: 300, width: 200, height: 200 });
  });

  it("normalises the rect when current is top-left of down", () => {
    const r = paintRectFrom({ x: 600, y: 500 }, { x: 400, y: 300 });
    expect(r).toEqual({ left: 400, top: 300, width: 200, height: 200 });
  });

  it("returns zero width/height for single-click (down == current)", () => {
    const r = paintRectFrom({ x: 250, y: 175 }, { x: 250, y: 175 });
    expect(r).toEqual({ left: 250, top: 175, width: 0, height: 0 });
  });

  it("is consistent across all four quadrants", () => {
    const down = { x: 500, y: 400 };
    for (const current of [
      { x: 700, y: 200 }, // up-right
      { x: 300, y: 600 }, // down-left
      { x: 700, y: 600 }, // down-right
      { x: 300, y: 200 }, // up-left
    ]) {
      const r = paintRectFrom(down, current);
      expect(r.width).toBe(Math.abs(current.x - down.x));
      expect(r.height).toBe(Math.abs(current.y - down.y));
      expect(r.left).toBe(Math.min(down.x, current.x));
      expect(r.top).toBe(Math.min(down.y, current.y));
    }
  });
});

describe("maybeSquareRect", () => {
  it("returns the input unchanged when square=false", () => {
    const r = { left: 100, top: 100, width: 200, height: 100 };
    expect(maybeSquareRect(r, { x: 100, y: 100 }, false)).toBe(r);
  });

  it("locks to a square anchored at down (drag down-right)", () => {
    const r = { left: 100, top: 100, width: 200, height: 100 };
    const out = maybeSquareRect(r, { x: 100, y: 100 }, true);
    expect(out).toEqual({ left: 100, top: 100, width: 200, height: 200 });
  });

  it("locks to a square anchored at down (drag up-left)", () => {
    // down=(300,300), current=(100,200) → raw rect = {100,200,200,100}
    const r = { left: 100, top: 200, width: 200, height: 100 };
    const out = maybeSquareRect(r, { x: 300, y: 300 }, true);
    // side = max(200,100) = 200; rect anchored at down corner (300) sliding
    // up-left so left=300-200=100, top=300-200=100.
    expect(out).toEqual({ left: 100, top: 100, width: 200, height: 200 });
  });
});

describe("ghostOutlineKind", () => {
  it("dispatches each known node type to a kind", () => {
    expect(ghostOutlineKind("concept")).toBe("rect");
    expect(ghostOutlineKind("entity")).toBe("circle");
    expect(ghostOutlineKind("funnel")).toBe("diamond");
    expect(ghostOutlineKind("area")).toBe("dashed");
    expect(ghostOutlineKind("note")).toBe("rect");
    expect(ghostOutlineKind("fact")).toBe("rect");
  });

  it("falls back to dashed for unknown / null", () => {
    expect(ghostOutlineKind(null)).toBe("dashed");
    expect(ghostOutlineKind("something-new")).toBe("dashed");
  });
});

describe("ghostIsSquare", () => {
  it("locks circle (entity) to square", () => {
    expect(ghostIsSquare("entity")).toBe(true);
  });
  it("does not lock other shapes", () => {
    expect(ghostIsSquare("concept")).toBe(false);
    expect(ghostIsSquare("funnel")).toBe(false);
    expect(ghostIsSquare("area")).toBe(false);
    expect(ghostIsSquare(null)).toBe(false);
  });
});

describe("PaintGhost render", () => {
  it("renders nothing when rect is null", () => {
    const { container } = render(<PaintGhost rect={null} nodeType="concept" />);
    expect(container.querySelector("[data-testid='paint-ghost']")).toBeNull();
  });

  it("renders nothing when nodeType is null", () => {
    const { container } = render(
      <PaintGhost rect={{ left: 0, top: 0, width: 10, height: 10 }} nodeType={null} />,
    );
    expect(container.querySelector("[data-testid='paint-ghost']")).toBeNull();
  });

  it("renders a positioned ghost for a sized rect", () => {
    render(
      <PaintGhost
        rect={{ left: 400, top: 300, width: 200, height: 200 }}
        nodeType="concept"
      />,
    );
    const ghost = screen.getByTestId("paint-ghost");
    expect(ghost.style.left).toBe("400px");
    expect(ghost.style.top).toBe("300px");
    expect(ghost.style.width).toBe("200px");
    expect(ghost.style.height).toBe("200px");
  });

  it("applies the diamond clip-path for funnel", () => {
    render(
      <PaintGhost
        rect={{ left: 0, top: 0, width: 100, height: 50 }}
        nodeType="funnel"
      />,
    );
    const ghost = screen.getByTestId("paint-ghost");
    expect(ghost.style.clipPath).toContain("polygon");
  });

  it("applies a 50% border-radius (circle) for entity", () => {
    render(
      <PaintGhost
        rect={{ left: 0, top: 0, width: 100, height: 100 }}
        nodeType="entity"
      />,
    );
    const ghost = screen.getByTestId("paint-ghost");
    expect(ghost.style.borderRadius).toBe("50%");
  });
});
