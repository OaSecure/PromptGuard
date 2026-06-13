import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

function read(relativePath) {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

test("dashboard pages expose consistent Korean navigation including server status", () => {
  const expectedLabels = ["대시보드", "이벤트 관리", "사용자 관리", "필터 관리", "서버 상태", "로그아웃"];
  const protectedPages = [
    ["overview", read("../overview.html")],
    ["events", read("../events.html")],
    ["event detail", read("../event-detail.html")],
    ["users", read("../users.html")],
    ["status", read("../static/status.js")],
    ["filters", `${read("../static/filters.js")}\n${read("../static/filtersPageModel.js")}`],
  ];

  for (const [pageName, pageSource] of protectedPages) {
    for (const label of expectedLabels) {
      assert.match(pageSource, new RegExp(label), `${pageName} navigation must include ${label}`);
    }
  }

  const surfaces = [read("../admin.html"), ...protectedPages.map(([, pageSource]) => pageSource)].join("\n");
  assert.doesNotMatch(surfaces, />Overview<\/a>|>Events<\/a>|>Users<\/a>|>Filters<\/a>|>Server Status<\/a>|>Logout<\/a>/);
  assert.doesNotMatch(surfaces, /href\s*=\s*["'](?:\.\/)?admin\.html["']/);
  assert.doesNotMatch(surfaces, /href\s*=\s*["'](?:\.\/)?index\.html["']/);
  assert.doesNotMatch(surfaces, /PromptGuard Dashboard|Loading status metadata|Authentication Required/);
  assert.doesNotMatch(surfaces, /Origin", "Kind", "Rule", "Severity", "Action", "Enabled", "Controls/);
  assert.doesNotMatch(surfaces, /Filter Rules를 불러오는 중입니다|Status metadata could not be loaded safely/);
  assert.doesNotMatch(surfaces, /프롬프트 해시|prompt_hash|request_fingerprint/);
});

test("static protected dashboard pages hide usable content until session verification", () => {
  for (const page of ["../overview.html", "../events.html", "../event-detail.html", "../users.html", "../filters.html", "../status.html"]) {
    const html = read(page);
    assert.match(html, /<body class="dashboard-auth-pending">/, `${page} must start in auth-pending state`);
  }

  const css = read("../static/main.css");
  assert.match(css, /\.dashboard-auth-pending\s+\.admin-header/);
  assert.match(css, /\.dashboard-auth-pending\s+\.dashboard/);
});
