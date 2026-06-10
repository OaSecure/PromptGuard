import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const overviewHtml = readFileSync(new URL("../overview.html", import.meta.url), "utf8");

test("overview shell preserves Korean dashboard design without static mock values", () => {
  assert.match(overviewHtml, /<title>OASecure 관리자 대시보드<\/title>/);
  assert.match(overviewHtml, /<h1>관리자 대시보드<\/h1>/);
  assert.match(overviewHtml, />이벤트 관리<\/a>/);
  assert.match(overviewHtml, />사용자 관리<\/a>/);
  assert.match(overviewHtml, />필터 관리<\/a>/);
  assert.match(overviewHtml, />서버 상태<\/a>/);
  assert.match(overviewHtml, />로그아웃<\/a>/);
  assert.match(overviewHtml, /type="module" src="\.\/static\/overview\.js"/);
  assert.doesNotMatch(overviewHtml, /<h1>Overview<\/h1>/);
  assert.doesNotMatch(overviewHtml, /PromptGuard event summary and risk activity/);
  assert.doesNotMatch(overviewHtml, />Logout<\/a>/);
  assert.doesNotMatch(overviewHtml, />Events<\/a>|>Users<\/a>|>Filters<\/a>|>Server Status<\/a>/);
  assert.doesNotMatch(overviewHtml, /Events in the selected period|Distinct login IDs|Most recent event timestamp/);
  assert.doesNotMatch(overviewHtml, />128<|>61<|>38<|>24</);
  assert.doesNotMatch(overviewHtml, /user01|user02|user03|guest/);
  assert.doesNotMatch(overviewHtml, /프롬프트 해시|prompt_hash|request_fingerprint/);
});
