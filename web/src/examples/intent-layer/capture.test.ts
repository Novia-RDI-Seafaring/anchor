import { describe, expect, it, vi } from "vitest";
import { captureTab, cropFrame } from "../../../examples/intent-layer/capture";
import { measureTargets, targetMetadata } from "../../../examples/intent-layer/metadata";

function captureFixture(surface = "browser") {
  const stop = vi.fn();
  const track = { stop, getSettings: () => ({ displaySurface: surface }) };
  const stream = { getVideoTracks: () => [track], getTracks: () => [track] } as unknown as MediaStream;
  const dispose = vi.fn(), encode = vi.fn(() => "data:image/png;base64,ACTUAL_FRAME_FIXTURE");
  const readFrame = vi.fn(async () => ({ width: 2000, height: 1200, encode, dispose }));
  return { stop, dispose, encode, readFrame, request: vi.fn(async () => stream),
    viewport: { width: 1000, height: 600 } };
}

describe("ordinary DOM screenshot capture", () => {
  it("scales CSS coordinates into frame pixels and clips partial viewport regions", () => {
    expect(cropFrame({ x: -10, y: 100.25, width: 120, height: 600 }, { width: 1000, height: 600 },
      { width: 2000, height: 1200 })).toEqual({
        crop: { x: 0, y: 100.25, width: 110, height: 499.75 },
        pixels: { x: 0, y: 200, width: 220, height: 1000 },
      });
    expect(() => cropFrame({ x: 1200, y: 0, width: 10, height: 10 }, { width: 1000, height: 600 },
      { width: 2000, height: 1200 })).toThrow("Scroll");
  });
  it("attaches the actual frame encoder result and stops sharing after capture", async () => {
    const deps = captureFixture();
    const result = await captureTab({ x: 20, y: 40, width: 100, height: 80 }, ["opaque/email"], deps);
    expect(result.status).toBe("attached");
    if (result.status === "attached") expect(result.screenshot).toMatchObject({
      targetIds: ["opaque/email"], capture: "browser-tab", dataUrl: "data:image/png;base64,ACTUAL_FRAME_FIXTURE",
      pixels: { x: 40, y: 80, width: 200, height: 160 },
    });
    expect(deps.encode).toHaveBeenCalledWith({ x: 40, y: 80, width: 200, height: 160 });
    expect(deps.stop).toHaveBeenCalledOnce(); expect(deps.dispose).toHaveBeenCalledOnce();
  });
  it("does not pretend window or screen captures match the tab coordinates", async () => {
    const deps = captureFixture("window");
    const result = await captureTab({ x: 0, y: 0, width: 10, height: 10 }, ["email"], deps);
    expect(result).toMatchObject({ status: "failed", message: expect.stringContaining("browser tab") });
    expect(deps.readFrame).not.toHaveBeenCalled(); expect(deps.stop).toHaveBeenCalledOnce();
  });
  it("honestly degrades on unsupported capture, denial, frame errors and encoding errors", async () => {
    const deps = captureFixture();
    expect(await captureTab({ x: 0, y: 0, width: 10, height: 10 }, [], { ...deps, request: undefined }))
      .toMatchObject({ status: "unavailable" });
    deps.request.mockRejectedValueOnce(new DOMException("Declined", "NotAllowedError"));
    expect(await captureTab({ x: 0, y: 0, width: 10, height: 10 }, [], deps)).toMatchObject({ status: "denied" });
    deps.readFrame.mockRejectedValueOnce(new Error("No video"));
    expect(await captureTab({ x: 0, y: 0, width: 10, height: 10 }, [], deps)).toMatchObject({ status: "failed" });
    expect(deps.stop).toHaveBeenCalledOnce();
    deps.encode.mockImplementationOnce(() => { throw new Error("Encoding failed"); });
    expect(await captureTab({ x: 0, y: 0, width: 10, height: 10 }, [], deps)).toMatchObject({ status: "failed" });
    expect(deps.stop).toHaveBeenCalledTimes(2); expect(deps.dispose).toHaveBeenCalledOnce();
  });
});

describe("stable DOM identities and optional development metadata", () => {
  it("measures data-intent-id regardless of missing private React source metadata", () => {
    const surface = document.createElement("section"), field = document.createElement("label");
    field.dataset.intentId = "account/email"; field.dataset.intentLabel = "Email";
    surface.append(field);
    surface.getBoundingClientRect = () => new DOMRect(40, 30, 500, 500);
    field.getBoundingClientRect = () => new DOMRect(100, 80, 200, 70);
    expect(measureTargets(surface, true)).toEqual([{
      id: "account/email", tag: "label", label: "Email",
      box: { id: "account/email", x: 60, y: 50, width: 200, height: 70 }, metadata: { mode: "dom" },
    }]);
    expect(measureTargets(surface, false)[0]).not.toHaveProperty("metadata");
  });
  it("bounds optional component/source lookup and never uses it as identity", () => {
    const field = document.createElement("label");
    Object.defineProperty(field, "__reactFiber$fixture", { enumerable: true, value: {
      return: { type: { name: "Field" }, _debugSource: { fileName: "C:/project/web/examples/form.tsx", lineNumber: 7 } },
    } });
    expect(targetMetadata(field, true)).toEqual({ mode: "component", component: "Field",
      source: { file: "web/examples/form.tsx", line: 7 } });
    expect(targetMetadata(field, false)).toBeUndefined();
    const broken = document.createElement("label");
    Object.defineProperty(broken, "__reactFiber$broken", { enumerable: true, get: () => { throw new Error("Unsupported Fiber"); } });
    expect(targetMetadata(broken, true)).toEqual({ mode: "dom" });
  });
});
