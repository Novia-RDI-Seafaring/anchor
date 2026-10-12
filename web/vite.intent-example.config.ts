import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react(), {
    name: "independent-form-boundary",
    resolveId(id) {
      if (id.startsWith("@/") || id.includes("@xyflow/") || /\/(canvas|stores|api)\//.test(id)) {
        throw new Error("The form example imported an Anchor application dependency: " + id);
      }
      return null;
    },
  }],
  server: { host: "127.0.0.1", port: 5193, strictPort: true,
    proxy: { "/form": { target: "http://127.0.0.1:8003", changeOrigin: false } } },
  build: { outDir: "dist/intent-example",
    rollupOptions: { input: fileURLToPath(new URL("./examples/intent-layer/index.html", import.meta.url)) } },
});
