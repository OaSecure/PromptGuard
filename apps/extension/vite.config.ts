import { copyFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const __dirname = dirname(fileURLToPath(import.meta.url));

function copyExtensionManifestPlugin() {
  return {
    name: "copy-extension-manifest",
    writeBundle() {
      copyFileSync(resolve(__dirname, "manifest.json"), resolve(__dirname, "dist/manifest.json"));
    }
  };
}

export default defineConfig({
  plugins: [copyExtensionManifestPlugin()],
  build: {
    outDir: "dist",
    emptyOutDir: false,
    rollupOptions: {
      input: {
        serviceWorker: resolve(__dirname, "src/background/serviceWorker.ts"),
        options: resolve(__dirname, "src/options/options.html")
      },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "chunks/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]"
      }
    }
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["tests/**/*.test.ts", "tests/**/*.spec.ts"]
  }
});
