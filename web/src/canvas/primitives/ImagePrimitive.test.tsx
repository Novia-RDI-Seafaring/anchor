/**
 * A picture on the board. The failure this guards against: a drawing that
 * belongs beside a card having nowhere to be.
 */
import { render } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ImagePrimitive, imageSrc } from "./ImagePrimitive";

function mount(data: Record<string, unknown>, selected = false) {
  return render(
    <MemoryRouter initialEntries={["/canvas/w1"]}>
      <Routes>
        <Route
          path="/canvas/:id"
          element={
            <ReactFlowProvider>
              <ImagePrimitive
                {...({
                  id: "img1",
                  data,
                  selected,
                  dragging: false,
                  isConnectable: false,
                  positionAbsoluteX: 0,
                  positionAbsoluteY: 0,
                  type: "image",
                  zIndex: 0,
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                } as any)}
              />
            </ReactFlowProvider>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ImagePrimitive", () => {
  it("shows a cut from a document page, by its page and bbox", () => {
    const src = imageSrc({
      source_ref: { slug: "lkh", page: 3, bbox: [48, 68, 305, 192] },
    });
    expect(src).toContain("/api/documents/lkh/pages/3/crop?");
    expect(src).toContain("bbox=48%2C68%2C305%2C192");
    const { container } = mount({
      label: "LKH-5 dimensions drawing",
      source_ref: { slug: "lkh", page: 3, bbox: [48, 68, 305, 192] },
    });
    const img = container.querySelector("img")!;
    expect(img.getAttribute("src")).toContain("/pages/3/crop");
    expect(img.getAttribute("alt")).toBe("LKH-5 dimensions drawing");
    expect(container.textContent).toContain("LKH-5 dimensions drawing");
  });

  it("shows a plain URL as it is", () => {
    expect(imageSrc({ src: "https://x/y.png" })).toBe("https://x/y.png");
  });

  it("says so, rather than breaking, when it has no picture", () => {
    expect(imageSrc({})).toBeNull();
    expect(imageSrc({ source_ref: { slug: "lkh", page: 3 } })).toBeNull();
    const { container } = mount({ label: "" });
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("no picture yet");
  });
});
