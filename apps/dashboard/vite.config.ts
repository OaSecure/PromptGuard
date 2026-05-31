import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        dashboard: "index.html",
        filters: "filters.html",
        status: "status.html"
      }
    }
  }
});
