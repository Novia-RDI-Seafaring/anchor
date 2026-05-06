const BASE = (import.meta.env.VITE_BACKEND_URL as string | undefined) ?? "";

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const rsp = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!rsp.ok) {
    const text = await rsp.text();
    throw new Error(`${method} ${path} → ${rsp.status}: ${text}`);
  }
  if (rsp.status === 204) return undefined as T;
  return rsp.json() as Promise<T>;
}

async function upload<T>(path: string, formData: FormData): Promise<T> {
  const rsp = await fetch(`${BASE}${path}`, {
    method: "POST",
    body: formData,
  });
  if (!rsp.ok) {
    const text = await rsp.text();
    throw new Error(`POST ${path} → ${rsp.status}: ${text}`);
  }
  if (rsp.status === 204) return undefined as T;
  return rsp.json() as Promise<T>;
}

export const api = {
  get: <T,>(path: string) => request<T>("GET", path),
  post: <T,>(path: string, body?: unknown) => request<T>("POST", path, body),
  patch: <T,>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  del: <T,>(path: string) => request<T>("DELETE", path),
  upload: <T,>(path: string, formData: FormData) => upload<T>(path, formData),
};

export const BACKEND_URL = BASE;
