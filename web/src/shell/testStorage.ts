/**
 * Test helper: swap `window.localStorage` for a working in-memory fake
 * (this project's jsdom setup ships a method-less stub) or a throwing
 * one (the private-mode / blocked-site-data case). Callers restore via
 * the returned function.
 */

export type FakeStorage = {
  getItem: (k: string) => string | null;
  setItem: (k: string, v: string) => void;
  removeItem: (k: string) => void;
  clear: () => void;
};

function swap(value: unknown): () => void {
  const original = Object.getOwnPropertyDescriptor(window, "localStorage");
  Object.defineProperty(window, "localStorage", {
    value,
    configurable: true,
  });
  return () => {
    if (original) Object.defineProperty(window, "localStorage", original);
    else delete (window as { localStorage?: unknown }).localStorage;
  };
}

export function installFakeStorage(): { storage: FakeStorage; restore: () => void } {
  const store = new Map<string, string>();
  const storage: FakeStorage = {
    getItem: (k) => (store.has(k) ? store.get(k)! : null),
    setItem: (k, v) => {
      store.set(k, String(v));
    },
    removeItem: (k) => {
      store.delete(k);
    },
    clear: () => store.clear(),
  };
  return { storage, restore: swap(storage) };
}

export function installThrowingStorage(): { restore: () => void } {
  const boom = () => {
    throw new Error("storage blocked");
  };
  return {
    restore: swap({ getItem: boom, setItem: boom, removeItem: boom, clear: boom }),
  };
}
