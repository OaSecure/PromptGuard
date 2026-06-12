import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const filtersJs = await readFile(new URL("../static/filters.js", import.meta.url), "utf8");
const mainCss = await readFile(new URL("../static/main.css", import.meta.url), "utf8");

test("filters screen keeps dry-run next to the rule form instead of nested inside it", () => {
  assert.match(filtersJs, /grid\.append\(renderForm\(\), renderDryRun\(\)\)/);
  assert.doesNotMatch(filtersJs, /form\.append\(renderDryRun\(\)\)/);
});

test("filters screen renders regex help as readable list items", () => {
  assert.match(filtersJs, /el\("ul", "filter-help-list"\)/);
  assert.match(filtersJs, /helpList\(filterRegexHelpItems\(\)\)/);
  assert.doesNotMatch(filtersJs, /el\("p", "filter-subtext", filterRegexHelpText\(\)\)/);
});

test("filters screen css supports side-by-side desktop layout and mobile fallback", () => {
  assert.match(mainCss, /\.filter-grid\s*{[\s\S]*grid-template-columns: minmax\(0, 1\.45fr\) minmax\(360px, 0\.8fr\)/);
  assert.match(mainCss, /\.filter-help-list\s*{[\s\S]*display: grid/);
  assert.match(mainCss, /@media \(max-width: 850px\)[\s\S]*\.filter-grid\s*{[\s\S]*grid-template-columns: 1fr/);
});
