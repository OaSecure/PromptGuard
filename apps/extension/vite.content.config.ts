import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: resolve(__dirname, "src/content/contentScript.ts"),
      output: {
        format: "iife",
        name: "PromptGuardContentScript",
        entryFileNames: "contentScript.js",
        assetFileNames: "assets/[name]-[hash][extname]"
      }
    }
  }
});
