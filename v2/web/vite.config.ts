import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: 5183,
    strictPort: true,  // fail loudly instead of auto-bumping into another dev server
    proxy: {
      // SSE-friendly: explicit changeOrigin + selfHandleResponse=false
      // and a hint to disable any nginx-style proxy buffering. Vite's
      // default shorthand sometimes holds onto chunked text/event-stream
      // responses; this passes them straight through.
      "/api": {
        target: "http://localhost:8002",
        changeOrigin: true,
        selfHandleResponse: false,
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            proxyRes.headers["x-accel-buffering"] = "no";
            proxyRes.headers["cache-control"] = "no-cache, no-transform";
          });
        },
      },
      "/ws": { target: "ws://localhost:8002", ws: true, changeOrigin: true },
      "/mcp": { target: "http://localhost:8002", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
