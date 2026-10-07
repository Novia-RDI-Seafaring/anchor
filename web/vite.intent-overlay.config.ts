import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/** Independent build: no Anchor alias, entry point, API or ReactFlow runtime. */
export default defineConfig({
  plugins: [react(), {
    name: "intent-overlay-boundary",
    resolveId(id) {
      if (id.startsWith("@/") || id.includes("@xyflow/") || /\/(canvas|stores|api)\//.test(id)) {
        throw new Error(`Intent overlay imported an application dependency: ${id}`);
      }
      return null;
    },
  }],
  build: {
    outDir: "dist/intent-overlay",
    lib: {
      entry: fileURLToPath(new URL("./src/intent-overlay/index.ts", import.meta.url)),
      formats: ["es"], fileName: "index", cssFileName: "styles",
    },
    rollupOptions: {
      external: ["react", "react/jsx-runtime", "zustand", "zustand/vanilla"],
    },
  },
});
