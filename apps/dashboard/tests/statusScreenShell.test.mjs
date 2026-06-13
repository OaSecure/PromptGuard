import test from "node:test";
import assert from "node:assert/strict";

const { renderStatusPlan } = await import("../static/statusPageModel.js");

test("status screen includes safe Chrome extension setup guidance", () => {
  const payload = {
    status: "healthy",
    last_checked: "2026-06-12T09:00:00Z",
    api_status: "healthy",
    postgres_status: "healthy",
    migration_status: "healthy",
    filter_rules_status: "healthy",
  };
  const plan = renderStatusPlan(payload, "http://localhost:3000");

  assert.equal(plan.extensionSetup.title, "Chrome 확장프로그램 연동");
  assert.deepEqual(plan.extensionSetup.settings, [
    {
      label: "API URL",
      value: "다른 PC 사용자에게는 서버 PC의 LAN IP, 도메인, 또는 포트포워딩 주소를 안내합니다.",
      description: "Chrome 확장프로그램은 이 주소에 /auth/login, /config/extension, /prompts/analyze 요청을 보냅니다. localhost는 서버 관리자 PC에서만 유효합니다.",
    },
    {
      label: "관리자 로컬 확인용",
      value: "http://localhost:8000",
      description: "서버를 띄운 같은 컴퓨터에서만 확인할 때 쓰는 주소입니다. 다른 사용자에게 이 값을 그대로 전달하지 않습니다.",
    },
    {
      label: "Mock API",
      value: "끔",
      description: "Mock API mode 체크를 해제해야 실제 PromptGuard 서버로 요청합니다.",
    },
    {
      label: "Login ID",
      value: "대시보드에서 생성한 사용자 ID 또는 로컬 기본 관리자 ID admin",
      description: "운영 환경에서는 사용자별 계정을 사용합니다.",
    },
    {
      label: "Password",
      value: "해당 계정의 비밀번호",
      description: "서버 상태 화면은 비밀번호 값을 표시하지 않습니다.",
    },
  ]);
  assert.deepEqual(plan.extensionSetup.steps, [
    "서버 배포자는 Chrome 확장프로그램 사용자의 컴퓨터에서 접속할 수 있는 백엔드 API origin을 확인합니다.",
    "다른 PC 사용자는 localhost가 아니라 서버 PC의 LAN IP, 도메인, 또는 외부로 열린 포트포워딩 주소를 API URL로 입력해야 합니다.",
    "옵션에서 Save를 눌러 API URL과 Mock API 설정을 저장합니다.",
    "Login ID와 Password로 확장프로그램 로그인을 실행합니다.",
    "Sync config를 눌러 서버의 확장 설정을 가져옵니다.",
    "이후 브라우저 입력창에서 Allow/Warn/Mask/Block 동작을 확인합니다.",
  ]);

  const encoded = JSON.stringify(plan);
  assert.doesNotMatch(encoded, /1234|access[_ -]?token|refresh[_ -]?token|secret|DB URL|DATABASE_URL|stack trace|selector/i);
});

test("status page renders API URL help in a dialog instead of crowding the card", async () => {
  const fs = await import("node:fs/promises");
  const statusJs = await fs.readFile(new URL("../static/status.js", import.meta.url), "utf8");

  assert.match(statusJs, /API URL 확인 방법/);
  assert.match(statusJs, /status-help-dialog/);
  assert.match(statusJs, /aria-modal/);
  assert.match(statusJs, /닫기/);
  assert.doesNotMatch(statusJs, /card\.append\(copy, settings, list\)/);
  assert.match(statusJs, /card\.append\(copy, settings, actions\)/);
});

test("status screen derives extension API URL from dashboard origin and documents port forwarding", () => {
  const payload = {
    status: "healthy",
    last_checked: "2026-06-12T09:00:00Z",
    api_status: "healthy",
    postgres_status: "healthy",
    migration_status: "healthy",
    filter_rules_status: "healthy",
  };

  const localPlan = renderStatusPlan(payload, "http://127.0.0.1:3000");
  assert.notEqual(localPlan.extensionSetup.settings[0].value, "http://127.0.0.1:8000");
  assert.equal(localPlan.extensionSetup.settings[1].value, "http://127.0.0.1:8000");

  const forwardedPlan = renderStatusPlan(payload, "https://promptguard.example.com");
  assert.equal(forwardedPlan.extensionSetup.settings[0].value, "https://promptguard.example.com");

  const encoded = JSON.stringify(forwardedPlan);
  assert.match(encoded, /Chrome 확장프로그램.*\/auth\/login.*\/config\/extension.*\/prompts\/analyze/);
  assert.match(encoded, /사용자의 컴퓨터에서 접속할 수 있는 백엔드 API origin/);
  assert.match(encoded, /localhost가 아니라 서버 PC의 LAN IP, 도메인, 또는 외부로 열린 포트포워딩 주소/);
  assert.doesNotMatch(encoded, /http:\/\/localhost:8000/);
});
