import { existsSync, readdirSync, readFileSync } from "node:fs";
import { extname, join } from "node:path";

const requiredFiles = [
  "index.html",
  "src/main.ts",
  "src/styles/main.css",
  "tsconfig.json",
  "vite.config.ts"
];

for (const file of requiredFiles) {
  if (!existsSync(file)) {
    console.error(`Missing dashboard file: ${file}`);
    process.exit(1);
  }
}

const scannedExtensions = new Set([".html", ".js", ".jsx", ".ts", ".tsx"]);
const ignoredDirectories = new Set(["dist", "node_modules"]);
const prohibited = [
  "raw_prompt",
  "rawPrompt",
  "prompt_text",
  "promptText",
  "prompt excerpt",
  "promptExcerpt",
  "masked_prompt",
  "maskedPrompt",
  "full masked prompt",
  "file_content",
  "fileContent",
  "extracted_text",
  "extractedText",
  "detected_raw_value",
  "detectedRawValue",
  "raw_detected_value",
  "rawDetectedValue",
  "original_filename",
  "originalFilename",
  "secret_value",
  "secretValue",
  "token_raw",
  "tokenRaw"
];

function listScannedFiles(directory) {
  const entries = readdirSync(directory, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const path = join(directory, entry.name);

    if (entry.isDirectory()) {
      if (!ignoredDirectories.has(entry.name)) {
        files.push(...listScannedFiles(path));
      }
      continue;
    }

    if (scannedExtensions.has(extname(entry.name))) {
      files.push(path);
    }
  }

  return files;
}

for (const file of listScannedFiles(".")) {
  const source = readFileSync(file, "utf8");

  if (source.includes("innerHTML")) {
    console.error(`Dashboard source uses innerHTML in ${file}; use DOM APIs and textContent for dynamic data.`);
    process.exit(1);
  }

  for (const term of prohibited) {
    if (source.includes(term)) {
      console.error(`Dashboard source exposes prohibited raw-data term "${term}" in ${file}`);
      process.exit(1);
    }
  }
}

console.log("Dashboard scaffold checks passed.");
