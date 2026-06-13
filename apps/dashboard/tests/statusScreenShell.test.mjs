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
    },
    ...overrides,
  };
}

function connectionCardByLabel(plan, label) {
  const card = plan.extensionSetup.connectionCards.find((item) => item.label === label);
  assert.ok(card, `missing connection card: ${label}`);
  return card;
}

test("status screen contract shows network addresses extension users can actually enter", () => {
  const plan = renderStatusPlan(statusPayload());
  const internal = connectionCardByLabel(plan, "내부망 연결 주소");
  const external = connectionCardByLabel(plan, "외부/포트포워딩 주소");
  const port = connectionCardByLabel(plan, "API 포트");

  assert.equal(plan.extensionSetup.title, "Chrome 확장프로그램 연동");
  assert.deepEqual(
    plan.extensionSetup.connectionCards.map((item) => item.label),
    ["내부망 연결 주소", "외부/포트포워딩 주소", "API 포트"]
  );
  assert.match(internal.value, /http:\/\/192\.168\.0\.10:8000/);
  assert.match(internal.value, /http:\/\/10\.0\.0\.8:8000/);
  assert.match(internal.description, /같은 공유기|사내망|내부망/);
  assert.match(external.description, /외부 접속.*API URL 확인 방법/);
  assert.match(external.value, /자동 감지 안 됨/);
  assert.match(external.description, /자동으로 확인하지 못했습니다/);
  assert.equal(port.value, "8000");

  const encoded = JSON.stringify(plan);
  assert.match(encoded, /포트포워딩|공인 IP|도메인|외부 포트/);
  assert.doesNotMatch(encoded, /Login ID|Password|Mock API|해당 계정의 비밀번호/);
  assert.doesNotMatch(encoded, /1234|access[_ -]?token|refresh[_ -]?token|secret|DB URL|DATABASE_URL|stack trace|selector/i);
});

test("status screen distinguishes local-admin localhost from extension-user address", () => {
  const plan = renderStatusPlan(statusPayload({
    extension_connection: {
      internal_api_origins: [],
      excluded_internal_api_origins: ["http://172.19.0.3:8000"],
      external_api_origin: null,
      admin_local_api_origin: "http://localhost:8000",
      api_port: "8000",
    },
  }));
  const encoded = JSON.stringify(plan);
  const internal = connectionCardByLabel(plan, "내부망 연결 주소");

  assert.match(encoded, /서버 내부망 IP를 확인할 수 없습니다/);
  assert.match(encoded, /관리자 로컬 확인용/);
  assert.match(encoded, /localhost는 서버 관리자 PC에서만 유효/);
  assert.doesNotMatch(internal.value, /localhost/);
});

test("status screen uses forwarded external origin when proxy or port forwarding exposes one", () => {
  const plan = renderStatusPlan(statusPayload({
    extension_connection: {
      internal_api_origins: ["http://192.168.0.10:8000"],
      excluded_internal_api_origins: [],
      external_api_origin: "https://promptguard.example.com:9443",
      admin_local_api_origin: "http://localhost:8000",
      api_port: "8000",
    },
  }));
  const external = connectionCardByLabel(plan, "외부/포트포워딩 주소");

  const encoded = JSON.stringify(plan);
  assert.equal(external.value, "https://promptguard.example.com:9443");
  assert.match(external.description, /자동 감지됨/);
  assert.match(external.description, /외부에서 접속할 Chrome 확장프로그램 사용자/);
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
    },
  }));
  const internal = connectionCardByLabel(plan, "내부망 연결 주소");
  const encoded = JSON.stringify(plan);

  assert.doesNotMatch(internal.value, /172\.19\.0\.3/);
  assert.match(encoded, /컨테이너 내부 주소는 제외됨/);
  assert.match(encoded, /http:\/\/172\.19\.0\.3:8000/);
});

test("status URL builder creates extension API origins from admin-entered host values", () => {
  assert.equal(buildLanApiOrigin("192.168.0.10", "8000"), "http://192.168.0.10:8000");
  assert.equal(buildLanApiOrigin(" 10.0.0.8 ", "8000"), "http://10.0.0.8:8000");
  assert.equal(buildLanApiOrigin("172.19.0.3", "8000"), "http://172.19.0.3:8000");
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
