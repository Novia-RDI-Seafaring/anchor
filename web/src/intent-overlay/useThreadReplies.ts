import { type Filed } from "./markupStore";
import { useEffect } from "react";
import { THREAD_POLL_MS } from "./constants";
import { filedFromIntent } from "./replyModel";
import type { MarkupModel } from "./types";

export function useThreadReplies(context: Pick<MarkupModel, "host" | "markupStore" | "filed">) {
  const { host, markupStore, filed } = context;
  // What was filed before this page loaded, rebuilt from the sketches the
  // server kept. Freehand ink does not survive a reload; the boxes do.
  useEffect(() => {
    let cancelled = false;
    void host.thread
      .loadScoped()
      .then((pending) => {
        if (cancelled) return;
        const mine = pending
          .map(filedFromIntent)
          .filter((f): f is Filed => f !== null);
        markupStore.getState().loadFiled(mine);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [host.thread, markupStore]);

  // The host nudges reads for local mutations and available server push.
  // Polling also catches independent writers, such as CLI or stdio MCP
  // processes, which do not share the serving process's notification bus.
  useEffect(() => {
    if (filed.length === 0) return undefined;
    let cancelled = false;
    const refresh = async () => {
      const latest = await Promise.all(
        filed.map(async (f) => {
          try {
            return await host.thread.get(f.intentId);
          } catch {
            return null;
          }
        }),
      );
      if (cancelled) return;
      markupStore.getState().refreshFiled(latest);
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), THREAD_POLL_MS);
    const onChanged = () => void refresh();
    const unsubscribe = host.thread.subscribeChanged(onChanged);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      unsubscribe();
    };
    // Re-arm when the SET of filed remarks changes, not on every poll result.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filed.map((f) => f.intentId).join("|"), host.thread]);

}
