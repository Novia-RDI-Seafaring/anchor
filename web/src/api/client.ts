const BASE = (import.meta.env.VITE_BACKEND_URL as string | undefined) ?? "";

export type UploadProgress = {
  loaded: number;
  total: number;
  percent: number;
};

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

async function upload<T>(
  path: string,
  formData: FormData,
  onProgress?: (progress: UploadProgress) => void,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}${path}`);
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable || !onProgress) return;
      onProgress({
        loaded: event.loaded,
        total: event.total,
        percent: Math.round((event.loaded / event.total) * 100),
      });
    };
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(`POST ${path} -> ${xhr.status}: ${xhr.responseText}`));
        return;
      }
      if (xhr.status === 204 || xhr.responseText.length === 0) {
        resolve(undefined as T);
        return;
      }
      try {
        resolve(JSON.parse(xhr.responseText) as T);
      } catch (err) {
        reject(err);
      }
    };
    xhr.onerror = () => reject(new Error(`POST ${path} failed`));
    xhr.onabort = () => reject(new Error(`POST ${path} aborted`));
    xhr.send(formData);
  });
}

export const api = {
  get: <T,>(path: string) => request<T>("GET", path),
  post: <T,>(path: string, body?: unknown) => request<T>("POST", path, body),
  patch: <T,>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  del: <T,>(path: string) => request<T>("DELETE", path),
  upload: <T,>(
    path: string,
    formData: FormData,
    onProgress?: (progress: UploadProgress) => void,
  ) => upload<T>(path, formData, onProgress),
};

export const BACKEND_URL = BASE;
