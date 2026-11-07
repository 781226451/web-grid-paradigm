import { fileURLToPath, URL } from "node:url";

import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

// The bundle is served by the Python control panel at the root path; the old
// hand-written page stays reachable at /legacy.
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
