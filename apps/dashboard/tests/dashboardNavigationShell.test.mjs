import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

function read(relativePath) {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

test("dashboard pages expose consistent Korean navigation including server status", () => {
  const surfaces = [
    read("../admin.html"),
    read("../overview.html"),
    read("../events.html"),
    read("../event-detail.html"),
    read("../users.html"),
    read("../static/status.js"),
    read("../static/filters.js"),
  ].join("\n");

  for (const label of ["대시보드", "이벤트 관리", "사용자 관리", "필터 관리", "서버 상태", "로그아웃"]) {
    assert.match(surfaces, new RegExp(label));
  }

  assert.doesNotMatch(surfaces, />Overview<\/a>|>Events<\/a>|>Users<\/a>|>Filters<\/a>|>Server Status<\/a>|>Logout<\/a>/);
  assert.doesNotMatch(surfaces, /href\s*=\s*["'](?:\.\/)?admin\.html["']/);
  assert.doesNotMatch(surfaces, /href\s*=\s*["'](?:\.\/)?index\.html["']/);
  assert.doesNotMatch(surfaces, /PromptGuard Dashboard|Loading status metadata|Authentication Required/);
  assert.doesNotMatch(surfaces, /Origin", "Kind", "Rule", "Severity", "Action", "Enabled", "Controls/);
  assert.doesNotMatch(surfaces, /Filter Rules를 불러오는 중입니다|Status metadata could not be loaded safely/);
  assert.doesNotMatch(surfaces, /프롬프트 해시|prompt_hash|request_fingerprint/);
});

test("status page navigation includes an active server status link", () => {
  const statusScript = read("../static/status.js");

  assert.match(statusScript, /appendText\(nav, "a", "서버 상태"\)/);
  assert.match(statusScript, /status\.href = "\.\/status\.html"/);
  assert.match(statusScript, /status\.className = "nav-button active"/);
  assert.match(statusScript, /nav\.append\(overview, events, users, filters, status, logout\)/);
});
