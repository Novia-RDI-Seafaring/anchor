import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { canvases, type WorkspaceMeta } from "@/api/canvases";

export function CanvasListPage() {
  const [items, setItems] = useState<WorkspaceMeta[]>([]);
  const [slug, setSlug] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  const refresh = () => canvases.list().then(setItems).catch(() => {});

  useEffect(() => {
    refresh();
  }, []);

  const create = async () => {
    if (!slug.trim()) return;
    setBusy(true);
    try {
      const meta = await canvases.create(slug.trim());
      navigate(`/c/${meta.slug}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-3xl font-bold">Anchor canvases</h1>
      <p className="mt-2 text-neutral-600">
        Each canvas is a folder. Pick one to open; create a new one below.
      </p>

      <div className="mt-8 flex gap-2">
        <input
          className="flex-1 rounded border border-neutral-300 px-3 py-2"
          placeholder="canvas slug — e.g. pump-analysis"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              void create();
            }
          }}
        />
        <button
          className="rounded bg-neutral-900 px-4 py-2 text-white disabled:opacity-50"
          disabled={busy}
          onClick={() => {
            void create();
          }}
        >
          Create
        </button>
      </div>

      <ul className="mt-10 space-y-2">
        {items.length === 0 ? (
          <li className="rounded border border-dashed border-neutral-300 p-6 text-center text-neutral-500">
            No canvases yet. Create one above.
          </li>
        ) : null}
        {items.map((m) => (
          <li key={m.slug}>
            <Link
              to={`/c/${m.slug}`}
              className="block rounded border border-neutral-200 bg-white px-4 py-3 hover:border-neutral-400"
            >
              <div className="font-medium">{m.title || m.slug}</div>
              <div className="text-xs text-neutral-500">{m.slug}</div>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
