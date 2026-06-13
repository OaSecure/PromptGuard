import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

test("events and event detail shells remove static mock internals and use module entrypoints", () => {
  const eventsHtml = readFileSync(new URL("../events.html", import.meta.url), "utf-8");
  const detailHtml = readFileSync(new URL("../event-detail.html", import.meta.url), "utf-8");

  assert.match(eventsHtml, /id="events-table-body"/);
  assert.match(detailHtml, /id="detail-summary-grid"/);
  const detailScript = readFileSync(new URL("../static/event-detail.js", import.meta.url), "utf-8");
  const detailCss = readFileSync(new URL("../static/main.css", import.meta.url), "utf-8");

  assert.match(detailScript, /event-summary-item/);
  assert.match(detailScript, /event-summary-label/);
  assert.match(detailScript, /event-summary-value/);
  assert.match(detailCss, /\.event-summary-item/);
  assert.match(detailCss, /\.event-summary-label/);
  assert.match(detailCss, /\.event-summary-value/);
  assert.match(eventsHtml, />서버 상태<\/a>/);
  assert.match(detailHtml, />서버 상태<\/a>/);
  assert.match(eventsHtml, /<h2>이벤트 요약<\/h2>/);
  assert.match(eventsHtml, /<h2>위험 이벤트<\/h2>/);
  assert.match(detailHtml, /<h2>업무 맥락<\/h2>/);
  assert.match(eventsHtml, /type="module" src="\.\/static\/events\.js"/);
  assert.match(detailHtml, /type="module" src="\.\/static\/event-detail\.js"/);
  assert.doesNotMatch(eventsHtml, />Overview<\/a>|>Events<\/a>|>Users<\/a>|>Filters<\/a>|>Server Status<\/a>|>Logout<\/a>/);
  assert.doesNotMatch(detailHtml, />Overview<\/a>|>Events<\/a>|>Users<\/a>|>Filters<\/a>|>Server Status<\/a>|>Logout<\/a>/);
  assert.doesNotMatch(eventsHtml, /김OO|박OO|이OO/);
  assert.doesNotMatch(eventsHtml, /event-detail\.html\?risk=/);
  assert.doesNotMatch(eventsHtml, /id="events-(?:total|block|mask|warn)-count">\d+</);
  assert.doesNotMatch(detailHtml, /프롬프트 해시/);
  assert.doesNotMatch(detailHtml, /ph_[a-z0-9]+/i);
});
