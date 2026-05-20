import { useEffect, useState } from "react";

import { useCanvasStore } from "@/stores/canvasStore";

const VISIBLE_MS = 3500;

export function ActivityToast() {
  const activity = useCanvasStore((s) => s.activity);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (activity.length === 0) return;
    const t = setInterval(() => setNow(Date.now()), 300);
    return () => clearInterval(t);
  }, [activity.length]);

  const fresh = activity.filter((a) => now - a.at < VISIBLE_MS);
  if (fresh.length === 0) return null;

  return (
    <div className="pointer-events-none absolute right-4 top-4 z-30 flex flex-col gap-1.5">
      {fresh.map((a) => {
        const age = now - a.at;
        const opacity = age < VISIBLE_MS - 600 ? 1 : Math.max(0, (VISIBLE_MS - age) / 600);
        return (
          <div
            key={a.id}
            style={{ opacity }}
            className="rounded-md border border-neutral-200 bg-white/95 px-3 py-1.5 text-xs font-medium text-neutral-700 shadow-sm backdrop-blur"
          >
            {a.text}
          </div>
        );
      })}
    </div>
  );
}
