/**
 * CanvasListPage — landing page rendered as a folder tree.
 *
 * The tree is derived from the canvas-reference graph: when canvas A
 * contains a `node_type === "canvas"` node whose `data.canvas_slug = "b"`,
 * B appears nested under A. The backend pre-computes the references and
 * the reverse map (see `WorkspaceService.list_workspaces`), so this page
 * does a single GET and renders.
 *
 * Cycles + DAGs are honoured. See `CanvasTree.tsx` for the rendering
 * rules.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { canvases, type WorkspaceListEntry } from "@/api/canvases";

import { CanvasTree } from "./CanvasTree";

export function CanvasListPage() {
  const [items, setItems] = useState<WorkspaceListEntry[]>([]);
  const [slug, setSlug] = useState("");
  const [busy, setBusy] = useState(false);
  const [deletingSlug, setDeletingSlug] = useState<string | null>(null);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const refresh = () => canvases.list().then(setItems).catch(() => {});

  useEffect(() => {
    refresh();
  }, []);

  const create = async () => {
    if (!slug.trim()) return;
    setBusy(true);
    setError("");
    try {
      const meta = await canvases.create(slug.trim());
      navigate(`/c/${meta.slug}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create canvas");
    } finally {
      setBusy(false);
    }
  };

  const deleteCanvas = async (item: WorkspaceListEntry) => {
    const title = item.title || item.slug;
    const confirmed = window.confirm(
      `Delete canvas "${title}"?\n\nThis removes the workspace and its saved nodes. Links from other canvases will show as missing.`,
    );
    if (!confirmed) return;
    setDeletingSlug(item.slug);
    setError("");
    try {
      await canvases.delete(item.slug);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete canvas");
    } finally {
      setDeletingSlug(null);
    }
  };

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-3xl font-bold">Anchor canvases</h1>
      <p className="mt-2 text-neutral-600">
        Each canvas is a folder. Nested canvases come from{" "}
        <code className="rounded bg-neutral-100 px-1 text-[12px]">canvas</code>
        {" "}nodes — drop one onto a parent to grow the tree.
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
          + New canvas
        </button>
      </div>
      {error ? (
        <p className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      <div className="mt-10">
        <CanvasTree items={items} onDelete={deleteCanvas} deletingSlug={deletingSlug} />
      </div>
    </main>
  );
}
