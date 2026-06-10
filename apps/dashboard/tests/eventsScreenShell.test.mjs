import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

test("events and event detail shells remove static mock internals and use module entrypoints", () => {
  const eventsHtml = readFileSync(new URL("../events.html", import.meta.url), "utf-8");
  const detailHtml = readFileSync(new URL("../event-detail.html", import.meta.url), "utf-8");

  assert.match(eventsHtml, /id="events-table-body"/);
  assert.match(detailHtml, /id="detail-summary-grid"/);
  assert.match(eventsHtml, /type="module" src="\.\/static\/events\.js"/);
  assert.match(detailHtml, /type="module" src="\.\/static\/event-detail\.js"/);
  assert.doesNotMatch(detailHtml, /프롬프트 해시/);
  assert.doesNotMatch(detailHtml, /ph_[a-z0-9]+/i);
});
