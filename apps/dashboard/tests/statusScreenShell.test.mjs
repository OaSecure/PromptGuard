import test from "node:test";
import assert from "node:assert/strict";

const {
  buildExternalApiOrigin,
  buildLanApiOrigin,
  renderStatusPlan,
} = await import("../static/statusPageModel.js");

function statusPayload(overrides = {}) {
  return {
    status: "healthy",
    last_checked: "2026-06-12T09:00:00Z",
    api_status: "healthy",
    postgres_status: "healthy",
    migration_status: "healthy",
    filter_rules_status: "healthy",
    extension_connection: {
      internal_api_origins: ["http://192.168.0.10:8000", "http://10.0.0.8:8000"],
      excluded_internal_api_origins: [],
      external_api_origin: null,
      admin_local_api_origin: "http://localhost:8000",
      api_port: "8000",
      extension_api_url: "http://192.168.0.25:8000",
      extension_api_url_status: "configured",
      extension_api_url_error: null,
      dashboard_public_url: "http://192.168.0.25:8000/dashboard/",
    },
    ...overrides,
  };
}

function connectionCardByLabel(plan, label) {
  const card = plan.extensionSetup.connectionCards.find((item) => item.label === label);
  assert.ok(card, `missing connection card: ${label}`);
  return card;
}

test("status screen contract shows explicitly configured extension API URL as the copyable value", () => {
  const plan = renderStatusPlan(statusPayload());
  const apiUrl = connectionCardByLabel(plan, "Chrome Extension API URL");
  const dashboardUrl = connectionCardByLabel(plan, "Dashboard URL");
  const detected = connectionCardByLabel(plan, "진단용 감지 주소");

  assert.equal(plan.extensionSetup.title, "Chrome 확장프로그램 연동");
  assert.deepEqual(
    plan.extensionSetup.connectionCards.map((item) => item.label),
    ["Chrome Extension API URL", "Dashboard URL", "진단용 감지 주소"]
  );
  assert.equal(apiUrl.value, "http://192.168.0.25:8000");
  assert.equal(apiUrl.copyValue, "http://192.168.0.25:8000");
  assert.equal(apiUrl.state, "ready");
  assert.equal(dashboardUrl.value, "http://192.168.0.25:8000/dashboard/");
  assert.match(detected.value, /자동 감지 안 됨/);
  assert.match(detected.description, /참고용/);

  const encoded = JSON.stringify(plan);
  assert.match(encoded, /PROMPTGUARD_EXTENSION_API_URL|포트포워딩|공인 IP|도메인|외부 포트/);
  assert.doesNotMatch(encoded, /Login ID|Password|Mock API|해당 계정의 비밀번호/);
  assert.doesNotMatch(encoded, /1234|access[_ -]?token|refresh[_ -]?token|secret|DB URL|DATABASE_URL|stack trace|selector/i);
});

test("status screen requires explicit extension API URL before showing a copy value", () => {
  const plan = renderStatusPlan(statusPayload({
    extension_connection: {
      internal_api_origins: ["http://192.168.0.10:8000"],
      excluded_internal_api_origins: [],
      external_api_origin: null,
      admin_local_api_origin: "http://localhost:8000",
      api_port: "8000",
      extension_api_url: null,
      extension_api_url_status: "missing",
      extension_api_url_error: "PROMPTGUARD_EXTENSION_API_URL is not configured.",
      dashboard_public_url: null,
    },
  }));
  const apiUrl = connectionCardByLabel(plan, "Chrome Extension API URL");

  assert.equal(apiUrl.value, "설정 필요");
  assert.equal(apiUrl.copyValue, undefined);
  assert.equal(apiUrl.state, "error");
  assert.match(apiUrl.description, /PROMPTGUARD_EXTENSION_API_URL/);
});

test("status screen treats invalid extension API URL as configuration error without copy value", () => {
  const plan = renderStatusPlan(statusPayload({
    extension_connection: {
      internal_api_origins: [],
      excluded_internal_api_origins: ["http://172.19.0.3:8000"],
      external_api_origin: null,
      admin_local_api_origin: "http://localhost:8000",
      api_port: "8000",
      extension_api_url: null,
      extension_api_url_status: "invalid",
      extension_api_url_error: "localhost only points to the user's own computer and cannot be used as the Extension API URL.",
      dashboard_public_url: "http://192.168.0.25:8000/dashboard/",
    },
  }));
  const apiUrl = connectionCardByLabel(plan, "Chrome Extension API URL");

  assert.equal(apiUrl.value, "설정 오류");
  assert.equal(apiUrl.copyValue, undefined);
  assert.equal(apiUrl.state, "error");
  assert.match(apiUrl.description, /localhost/);
});

test("status screen distinguishes local-admin localhost from extension-user address", () => {
  const plan = renderStatusPlan(statusPayload({
    extension_connection: {
      internal_api_origins: [],
      excluded_internal_api_origins: ["http://172.19.0.3:8000"],
      external_api_origin: null,
      admin_local_api_origin: "http://localhost:8000",
      api_port: "8000",
      extension_api_url: null,
      extension_api_url_status: "missing",
      extension_api_url_error: "PROMPTGUARD_EXTENSION_API_URL is not configured.",
      dashboard_public_url: null,
    },
  }));
  const encoded = JSON.stringify(plan);
  const apiUrl = connectionCardByLabel(plan, "Chrome Extension API URL");

  assert.match(encoded, /PROMPTGUARD_EXTENSION_API_URL/);
  assert.match(encoded, /관리자 로컬 확인용/);
  assert.match(encoded, /localhost는 서버 관리자 PC에서만 유효/);
  assert.doesNotMatch(apiUrl.value, /localhost/);
});

test("status screen uses forwarded external origin when proxy or port forwarding exposes one", () => {
  const plan = renderStatusPlan(statusPayload({
    extension_connection: {
      internal_api_origins: ["http://192.168.0.10:8000"],
      excluded_internal_api_origins: [],
      external_api_origin: "https://promptguard.example.com:9443",
      admin_local_api_origin: "http://localhost:8000",
      api_port: "8000",
      extension_api_url: "https://promptguard.example.com:9443",
      extension_api_url_status: "configured",
      extension_api_url_error: null,
      dashboard_public_url: "https://promptguard.example.com/dashboard/",
    },
  }));
  const detected = connectionCardByLabel(plan, "진단용 감지 주소");
  const apiUrl = connectionCardByLabel(plan, "Chrome Extension API URL");

  const encoded = JSON.stringify(plan);
  assert.equal(apiUrl.value, "https://promptguard.example.com:9443");
  assert.equal(apiUrl.copyValue, "https://promptguard.example.com:9443");
  assert.equal(detected.value, "https://promptguard.example.com:9443");
  assert.match(detected.description, /자동 감지됨/);
});

test("status help contract teaches non-expert admins to find IP and port forwarding on Windows macOS and Linux", () => {
  const plan = renderStatusPlan(statusPayload());
  const encoded = JSON.stringify(plan.extensionSetup.helpSections);

  assert.match(encoded, /Chrome 확장프로그램.*\/auth\/login.*\/config\/extension.*\/prompts\/analyze/);
  assert.match(encoded, /Windows/);
  assert.match(encoded, /ipconfig/);
  assert.match(encoded, /IPv4/);
  assert.match(encoded, /macOS/);
  assert.match(encoded, /시스템 설정|ifconfig|getifaddr/);
  assert.match(encoded, /Linux/);
  assert.match(encoded, /ip addr|hostname -I/);
  assert.match(encoded, /공유기 관리자 페이지|포트포워딩|외부 포트|내부 포트|방화벽/);
});

test("status screen keeps connection cards concise and moves operating-system steps into help", () => {
  const plan = renderStatusPlan(statusPayload());
  const cardText = JSON.stringify(plan.extensionSetup.connectionCards);
  const helpText = JSON.stringify(plan.extensionSetup.helpSections);

  assert.doesNotMatch(cardText, /ipconfig|hostname -I|ip addr|공유기 관리자 페이지|방화벽/);
  assert.match(helpText, /ipconfig/);
  assert.match(helpText, /hostname -I|ip addr/);
  assert.match(helpText, /공유기 관리자 페이지|방화벽/);
});

test("status screen excludes Docker bridge origins from recommended cards but explains why", () => {
  const plan = renderStatusPlan(statusPayload({
    extension_connection: {
      internal_api_origins: [],
      excluded_internal_api_origins: ["http://172.19.0.3:8000"],
      external_api_origin: null,
      admin_local_api_origin: "http://localhost:8000",
      api_port: "8000",
      extension_api_url: null,
      extension_api_url_status: "missing",
      extension_api_url_error: "PROMPTGUARD_EXTENSION_API_URL is not configured.",
      dashboard_public_url: null,
    },
  }));
  const apiUrl = connectionCardByLabel(plan, "Chrome Extension API URL");
  const encoded = JSON.stringify(plan);

  assert.doesNotMatch(apiUrl.value, /172\.19\.0\.3/);
  assert.match(encoded, /컨테이너 내부 주소는 제외됨/);
  assert.match(encoded, /http:\/\/172\.19\.0\.3:8000/);
});

test("status URL builder creates extension API origins from admin-entered host values", () => {
  assert.equal(buildLanApiOrigin("192.168.0.10", "8000"), "http://192.168.0.10:8000");
  assert.equal(buildLanApiOrigin(" 10.0.0.8 ", "8000"), "http://10.0.0.8:8000");
  assert.equal(buildLanApiOrigin("172.19.0.3", "8000"), null);
  assert.equal(buildLanApiOrigin("localhost", "8000"), null);
  assert.equal(buildLanApiOrigin("999.1.1.1", "8000"), null);

  assert.equal(buildExternalApiOrigin("promptguard.example.com", "9443", false), "http://promptguard.example.com:9443");
  assert.equal(buildExternalApiOrigin("promptguard.example.com", "443", true), "https://promptguard.example.com");
  assert.equal(buildExternalApiOrigin("https://promptguard.example.com/app", "443", true), "https://promptguard.example.com");
  assert.equal(buildExternalApiOrigin("http://203.0.113.10", "18000", false), "http://203.0.113.10:18000");
  assert.equal(buildExternalApiOrigin("bad host name", "8000", false), null);
  assert.equal(buildExternalApiOrigin("promptguard.example.com", "70000", false), null);
});

test("status API URL dialog keeps internal and external builders separated to avoid oversized modal", async () => {
  const fs = await import("node:fs/promises");
  const statusJs = await fs.readFile(new URL("../static/status.js", import.meta.url), "utf8");
  const mainCss = await fs.readFile(new URL("../static/main.css", import.meta.url), "utf8");

  assert.match(statusJs, /내부망 주소 만들기/);
  assert.match(statusJs, /외부망 주소 만들기/);
  assert.match(statusJs, /status-url-builder-mode/);
  assert.match(statusJs, /hidden = mode !== "lan"/);
  assert.match(statusJs, /hidden = mode !== "external"/);
  assert.match(mainCss, /max-height:\s*calc\(100vh - 48px\)/);
  assert.match(mainCss, /overflow-y:\s*auto/);
});
