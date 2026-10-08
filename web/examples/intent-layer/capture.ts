export type Rect = { x: number; y: number; width: number; height: number };
export type Size = { width: number; height: number };
export type Screenshot = {
  mime: "image/png";
  dataUrl: string;
  capture: "browser-tab";
  crop: Rect;
  pixels: Rect;
  viewport: Size;
  targetIds: string[];
};
export type CaptureResult =
  | { status: "attached"; screenshot: Screenshot }
  | { status: "unavailable" | "denied" | "failed"; message: string };
type Frame = { width: number; height: number; encode(crop: Rect): string; dispose(): void };
export type CaptureDependencies = {
  request?: () => Promise<MediaStream>;
  readFrame(stream: MediaStream): Promise<Frame>;
  viewport: Size;
};

/** Browser capture pixels can differ from CSS viewport units due to scaling. */
export function cropFrame(region: Rect, viewport: Size, frame: Size): { crop: Rect; pixels: Rect } {
  if (![viewport.width, viewport.height, frame.width, frame.height].every((n) => Number.isFinite(n) && n > 0) ||
      ![region.x, region.y, region.width, region.height].every(Number.isFinite) ||
      region.width <= 0 || region.height <= 0) throw new Error("Capture geometry is unavailable.");
  const left = Math.max(0, region.x);
  const top = Math.max(0, region.y);
  const right = Math.min(viewport.width, region.x + region.width);
  const bottom = Math.min(viewport.height, region.y + region.height);
  if (right <= left || bottom <= top) throw new Error("Scroll the fields into view before capturing.");
  const sx = frame.width / viewport.width, sy = frame.height / viewport.height;
  const px = Math.floor(left * sx), py = Math.floor(top * sy);
  return {
    crop: { x: left, y: top, width: right - left, height: bottom - top },
    pixels: { x: px, y: py, width: Math.ceil(right * sx) - px, height: Math.ceil(bottom * sy) - py },
  };
}

async function readBrowserFrame(stream: MediaStream): Promise<Frame> {
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.srcObject = stream;
  const dispose = () => { video.pause(); video.srcObject = null; video.remove(); };
  try {
    await video.play();
    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(() => reject(new Error("No browser frame arrived. Try capture again.")), 3000);
      const done = () => { window.clearTimeout(timer); resolve(); };
      if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(done);
      else window.requestAnimationFrame(done);
    });
    if (!video.videoWidth || !video.videoHeight) throw new Error("The browser returned an empty capture frame.");
    return {
      width: video.videoWidth, height: video.videoHeight, dispose,
      encode: (crop) => {
        const canvas = document.createElement("canvas");
        canvas.width = crop.width; canvas.height = crop.height;
        const context = canvas.getContext("2d");
        if (!context) throw new Error("PNG capture is unavailable in this browser.");
        context.drawImage(video, crop.x, crop.y, crop.width, crop.height, 0, 0, crop.width, crop.height);
        return canvas.toDataURL("image/png");
      },
    };
  } catch (error) { dispose(); throw error; }
}

function browserDependencies(): CaptureDependencies {
  const devices = navigator.mediaDevices;
  return {
    viewport: { width: window.innerWidth, height: window.innerHeight },
    request: devices?.getDisplayMedia ? () => devices.getDisplayMedia({
      video: { displaySurface: "browser" }, audio: false,
      preferCurrentTab: true, selfBrowserSurface: "include",
    } as DisplayMediaStreamOptions & { preferCurrentTab: boolean; selfBrowserSurface: string }) : undefined,
    readFrame: readBrowserFrame,
  };
}

/** Must be called by an explicit user gesture. Never reconstruct DOM pixels. */
export async function captureTab(region: Rect, targetIds: string[], deps = browserDependencies()): Promise<CaptureResult> {
  if (!deps.request) return { status: "unavailable", message: "Tab capture is unavailable. IDs and geometry still work." };
  let stream: MediaStream | undefined;
  let frame: Frame | undefined;
  try {
    stream = await deps.request();
    if (stream.getVideoTracks()[0]?.getSettings().displaySurface !== "browser") {
      throw new Error("Choose this browser tab, not a window or screen, so the crop matches the fields.");
    }
    frame = await deps.readFrame(stream);
    const geometry = cropFrame(region, deps.viewport, frame);
    const dataUrl = frame.encode(geometry.pixels);
    if (!dataUrl.startsWith("data:image/png;base64,")) throw new Error("No PNG frame was captured.");
    return { status: "attached", screenshot: {
      mime: "image/png", dataUrl, capture: "browser-tab", ...geometry,
      viewport: { ...deps.viewport }, targetIds: [...targetIds],
    } };
  } catch (error) {
    const denied = error instanceof DOMException && (error.name === "NotAllowedError" || error.name === "SecurityError");
    return { status: denied ? "denied" : "failed",
      message: denied ? "Capture was declined. No screenshot attached; IDs and geometry still work."
        : error instanceof Error ? error.message : "Capture failed. No screenshot attached." };
  } finally {
    frame?.dispose();
    for (const track of stream?.getTracks() ?? []) track.stop();
  }
}
