import { existsSync, readFileSync } from "node:fs";

const requiredFiles = [
  "index.html",
  "src/main.ts",
  "src/styles/main.css"
];

for (const file of requiredFiles) {
  if (!existsSync(file)) {
    console.error(`Missing dashboard file: ${file}`);
    process.exit(1);
  }
}

const source = readFileSync("src/main.ts", "utf8");
const prohibited = ["raw_prompt", "masked_prompt", "detected_raw_value", "original_filename"];

for (const term of prohibited) {
  if (source.includes(term)) {
    console.error(`Dashboard source exposes prohibited raw-data term: ${term}`);
    process.exit(1);
  }
}

console.log("Dashboard scaffold checks passed.");
