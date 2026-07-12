import { CircleCheck, CircleX, RefreshCw, ServerCog } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { runtimeStatus, type ExtensionStatusPayload } from "@/api/status";

export function ExtensionStatusPanel() {
  const [status, setStatus] = useState<ExtensionStatusPayload | null>(null);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setError("");
    try {
      setStatus(await runtimeStatus.getExtensions());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Runtime status unavailable");
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <section aria-label="Extension runtime status" className="mt-6 border-y border-neutral-200 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <ServerCog aria-hidden="true" className="h-5 w-5 shrink-0 text-neutral-500" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-neutral-900">Extension runtimes</h2>
            {status ? (
              <span className="text-xs text-neutral-500">
                {status.summary.available} available, {status.summary.unavailable} unavailable
              </span>
            ) : null}
          </div>
          {error ? (
            <p className="truncate text-xs text-red-700" title={error}>
              Runtime status unavailable
            </p>
          ) : null}
          {!status && !error ? (
            <p className="text-xs text-neutral-500">Checking bundled extensions...</p>
          ) : null}
        </div>
        <button
          type="button"
          aria-label="Refresh extension status"
          title="Refresh extension status"
          className="grid h-8 w-8 shrink-0 place-items-center rounded border border-neutral-200 text-neutral-600 hover:bg-neutral-100 disabled:opacity-50"
          disabled={refreshing}
          onClick={() => void refresh()}
        >
          <RefreshCw aria-hidden="true" className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
        </button>
      </div>

      {status ? (
        <ul className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
          {status.extensions.map((extension) => (
            <li key={extension.name} className="flex min-w-0 items-start gap-2 text-xs">
              {extension.available ? (
                <CircleCheck aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" />
              ) : (
                <CircleX aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-red-700" />
              )}
              <span className="min-w-0">
                <span className="block font-medium text-neutral-800">{extension.name}</span>
                <span
                  className="block truncate text-neutral-500"
                  title={extension.reason ?? (extension.available ? "Available" : "Unavailable")}
                >
                  {extension.available ? "Available" : extension.reason ?? "Unavailable"}
                </span>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
