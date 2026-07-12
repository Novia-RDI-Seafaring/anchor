import { api } from "./client";

export type ExtensionRuntimeStatus = {
  name: string;
  source: string;
  available: boolean;
  reason: string | null;
  error_type: string | null;
};

export type ExtensionStatusPayload = {
  extensions: ExtensionRuntimeStatus[];
  summary: {
    available: number;
    unavailable: number;
  };
};

export const runtimeStatus = {
  getExtensions: () => api.get<ExtensionStatusPayload>("/api/extensions/status"),
};
