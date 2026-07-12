import { useCallback, useRef, useState, type DragEvent } from "react";

import { canvases } from "@/api/canvases";

type FlowPosition = { x: number; y: number };
type ScreenToFlowPosition = (point: FlowPosition) => FlowPosition;

export type UploadJob = {
  id: string;
  filename: string;
  percent: number;
  status: "uploading" | "starting_ingest" | "failed";
  left: number;
  top: number;
  error?: string;
};

export function shortId(): string {
  return Math.random().toString(36).slice(2, 10);
}

export function useCanvasDrop(slug: string, screenToFlowPosition: ScreenToFlowPosition) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [uploadJobs, setUploadJobs] = useState<Record<string, UploadJob>>({});

  const onDragOver = useCallback((event: DragEvent) => {
    const types = event.dataTransfer.types;
    const accepted = types.includes("Files")
      || types.includes("application/x-anchor-node")
      || types.includes("application/x-anchor-canvas-link");
    if (!accepted) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  }, []);

  const onDrop = useCallback(async (event: DragEvent) => {
    const flowPosition = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    const canvasLink = event.dataTransfer.getData("application/x-anchor-canvas-link");
    if (canvasLink) {
      event.preventDefault();
      await attachCanvasLink(slug, canvasLink, flowPosition);
      return;
    }

    const nodePayload = event.dataTransfer.getData("application/x-anchor-node");
    if (nodePayload) {
      event.preventDefault();
      await addDroppedNode(slug, nodePayload, flowPosition);
      return;
    }

    if (!event.dataTransfer.files?.length) return;
    event.preventDefault();
    const rootRect = rootRef.current?.getBoundingClientRect();
    const screenPosition = {
      left: rootRect ? event.clientX - rootRect.left : event.clientX,
      top: rootRect ? event.clientY - rootRect.top : event.clientY,
    };
    const pdfs = Array.from(event.dataTransfer.files).filter((file) => (
      file.name.toLowerCase().endsWith(".pdf")
    ));
    await Promise.all(pdfs.map((file, index) => uploadPdf({
      slug,
      file,
      index,
      flowPosition,
      screenPosition,
      setUploadJobs,
    })));
  }, [screenToFlowPosition, slug]);

  return { rootRef, onDragOver, onDrop, uploadJobs };
}

async function attachCanvasLink(slug: string, raw: string, position: FlowPosition) {
  try {
    const link = JSON.parse(raw) as { slug: string; title: string };
    if (!link.slug || link.slug === slug) return;
    await canvases.addNode(slug, {
      node_type: "canvas",
      label: link.title || link.slug,
      x: position.x,
      y: position.y,
      data: { canvas_slug: link.slug, title: link.title || link.slug },
    });
  } catch (error) {
    console.error("canvas-link drop failed", error);
  }
}

async function addDroppedNode(slug: string, raw: string, position: FlowPosition) {
  try {
    const spec = JSON.parse(raw) as {
      node_type: string;
      label?: string;
      width?: number;
      height?: number;
      data?: Record<string, unknown>;
    };
    if (spec.data?.__create_sub_canvas) {
      const childSlug = `${slug}-sub-${shortId()}`;
      const title = (spec.data.title as string | undefined) ?? spec.label ?? "Sub-canvas";
      await canvases.createSubCanvas(slug, {
        slug: childSlug,
        title,
        x: position.x,
        y: position.y,
      });
      return;
    }

    const response = await canvases.addNode(slug, {
      ...spec,
      x: position.x,
      y: position.y,
    }) as { event?: { payload?: { id?: string } } } | null;
    const nodeId = response?.event?.payload?.id;
    const sourceNodeId = spec.data?.source_doc_node_id as string | undefined;
    const sourceRef = spec.data?.source_ref as Record<string, unknown> | undefined;
    if (!nodeId || !sourceNodeId) return;
    await canvases.addEdge(slug, {
      source: nodeId,
      target: sourceNodeId,
      edge_type: "anchored",
      data: {
        kind: "evidence",
        ...(sourceRef ? { source_ref: sourceRef } : {}),
        ...(spec.data?.source_region_id ? {
          source_region_id: spec.data.source_region_id,
        } : {}),
      },
    });
  } catch (error) {
    console.error("node drop failed", error);
  }
}

type UploadPdfArgs = {
  slug: string;
  file: File;
  index: number;
  flowPosition: FlowPosition;
  screenPosition: { left: number; top: number };
  setUploadJobs: React.Dispatch<React.SetStateAction<Record<string, UploadJob>>>;
};

async function uploadPdf({
  slug,
  file,
  index,
  flowPosition,
  screenPosition,
  setUploadJobs,
}: UploadPdfArgs) {
  const id = `upload-${Date.now()}-${index}-${shortId()}`;
  const yOffset = index * 36;
  setUploadJobs((jobs) => ({
    ...jobs,
    [id]: {
      id,
      filename: file.name,
      percent: 0,
      status: "uploading",
      left: screenPosition.left,
      top: screenPosition.top + yOffset,
    },
  }));
  try {
    await canvases.uploadFile(slug, file, flowPosition.x, flowPosition.y + yOffset, {
      onProgress: (progress) => updateUpload(setUploadJobs, id, { percent: progress.percent }),
    });
    updateUpload(setUploadJobs, id, { percent: 100, status: "starting_ingest" });
    window.setTimeout(() => removeUpload(setUploadJobs, id), 1500);
  } catch (error) {
    console.error("upload failed", error);
    updateUpload(setUploadJobs, id, {
      status: "failed",
      error: error instanceof Error ? error.message : String(error),
    });
    window.setTimeout(() => removeUpload(setUploadJobs, id), 6000);
  }
}

function updateUpload(
  setUploadJobs: UploadPdfArgs["setUploadJobs"],
  id: string,
  patch: Partial<UploadJob>,
) {
  setUploadJobs((jobs) => {
    const current = jobs[id];
    return current ? { ...jobs, [id]: { ...current, ...patch } } : jobs;
  });
}

function removeUpload(setUploadJobs: UploadPdfArgs["setUploadJobs"], id: string) {
  setUploadJobs((jobs) => {
    const { [id]: _removed, ...remaining } = jobs;
    return remaining;
  });
}
