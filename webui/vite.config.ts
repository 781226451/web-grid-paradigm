import { fileURLToPath, URL } from "node:url";

import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

// The bundle is served by the Python control panel at the root path.
export default defineConfig({
  base: "/",
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    outDir: "../src/web_grid_paradigm/panel/static",
    emptyOutDir: true,
    target: "chrome100",
    assetsDir: "assets",
    sourcemap: false,
    rollupOptions: {
      output: {
        // Keep the framework/UI library in stable chunks: they rarely change,
        // so a rebuild only invalidates the small application chunk.
        manualChunks(id: string): string | undefined {
          if (id.includes("node_modules/naive-ui") || id.includes("node_modules/vueuc")) {
            return "naive-ui";
          }
          if (id.includes("node_modules/@vue/") || id.includes("node_modules/vue/")) {
            return "vue";
          }
          return undefined;
        },
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/events": { target: "http://127.0.0.1:8765", changeOrigin: true },
    },
  },
});
