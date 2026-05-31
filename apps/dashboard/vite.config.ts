import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        dashboard: "index.html",
        status: "status.html"
      }
    }
  }
});
