import test from "node:test";
import assert from "node:assert/strict";

const {
  dashboardFallbackMessage,
  dashboardFallbackRole,
  dashboardFallbackState,
} = await import("../static/dashboardFallback.js");

test("dashboard fallback messages are shared across protected pages", () => {
  assert.equal(dashboardFallbackMessage("loading"), "데이터를 불러오는 중입니다.");
  assert.equal(dashboardFallbackMessage("empty"), "표시할 데이터가 없습니다.");
  assert.equal(dashboardFallbackMessage("error", 401), "대시보드 로그인이 필요합니다.");
  assert.equal(dashboardFallbackMessage("error", 403), "대시보드 로그인이 필요합니다.");
  assert.equal(dashboardFallbackMessage("error", 0), "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
  assert.equal(dashboardFallbackMessage("error", 500), "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.");
});

test("dashboard fallback state never exposes backend details", () => {
  const state = dashboardFallbackState("error", {
    status: 500,
    detail: "raw prompt token secret DATABASE_URL stack trace",
  });

  assert.deepEqual(state, {
    kind: "error",
    message: "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
    role: "alert",
    ariaLive: "assertive",
  });
});

test("dashboard fallback roles are consistent", () => {
  assert.equal(dashboardFallbackRole("loading"), "status");
  assert.equal(dashboardFallbackRole("empty"), "status");
  assert.equal(dashboardFallbackRole("ready"), "status");
  assert.equal(dashboardFallbackRole("error"), "alert");
});
