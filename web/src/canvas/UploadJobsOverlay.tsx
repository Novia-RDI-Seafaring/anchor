import type { UploadJob } from "@/canvas/useCanvasDrop";

export function UploadJobsOverlay({ jobs }: { jobs: Record<string, UploadJob> }) {
  return Object.values(jobs).map((job) => {
    const failed = job.status === "failed";
    const label = job.status === "starting_ingest"
      ? "Upload complete, starting ingest"
      : failed
        ? "Upload failed"
        : `Uploading ${job.percent}%`;
    return (
      <div
        key={job.id}
        className={`pointer-events-none absolute z-40 w-64 -translate-x-1/2 -translate-y-full rounded-md border bg-white/95 px-3 py-2 text-xs shadow-lg backdrop-blur ${
          failed ? "border-red-300 text-red-800" : "border-sky-200 text-neutral-700"
        }`}
        style={{ left: job.left, top: job.top }}
      >
        <div className="mb-1 flex items-center justify-between gap-3">
          <span className="truncate font-medium">{job.filename}</span>
          <span className="shrink-0 tabular-nums">{job.percent}%</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-neutral-200">
          <div
            className={failed ? "h-full bg-red-500" : "h-full bg-sky-500"}
            style={{ width: `${Math.max(0, Math.min(100, job.percent))}%` }}
          />
        </div>
        <div className="mt-1 truncate text-[10px]">{job.error ?? label}</div>
      </div>
    );
  });
}
