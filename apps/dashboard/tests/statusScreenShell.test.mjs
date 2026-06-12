import test from "node:test";
import assert from "node:assert/strict";

const { renderStatusPlan } = await import("../static/statusPageModel.js");

test("status screen includes safe Chrome extension setup guidance", () => {
  const plan = renderStatusPlan({
    status: "healthy",
    last_checked: "2026-06-12T09:00:00Z",
    api_status: "healthy",
    postgres_status: "healthy",
    migration_status: "healthy",
    filter_rules_status: "healthy",
  });

  assert.equal(plan.extensionSetup.title, "Chrome 확장프로그램 연동");
  assert.deepEqual(plan.extensionSetup.steps, [
    "확장프로그램 옵션에서 API URL을 현재 PromptGuard API 주소로 설정합니다.",
    "Mock 모드는 끄고 실제 API 모드로 전환합니다.",
    "확장프로그램에서 로그인한 뒤 설정 동기화를 실행합니다.",
    "이후 브라우저 입력창에서 Allow/Warn/Mask/Block 동작을 확인합니다.",
  ]);

  const encoded = JSON.stringify(plan);
  assert.doesNotMatch(encoded, /token|secret|password|DB URL|DATABASE_URL|stack trace|selector/i);
});
