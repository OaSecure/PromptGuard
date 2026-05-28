import { copyFileSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";

rmSync("dist", { force: true, recursive: true });
mkdirSync("dist", { recursive: true });
mkdirSync("dist/src", { recursive: true });
const html = readFileSync("index.html", "utf8").replace("./src/main.ts", "./src/main.js");
writeFileSync("dist/index.html", html);
copyFileSync("src/main.ts", "dist/src/main.js");
mkdirSync("dist/src/styles", { recursive: true });
copyFileSync("src/styles/main.css", "dist/src/styles/main.css");

console.log("Dashboard static bundle written to dist.");
