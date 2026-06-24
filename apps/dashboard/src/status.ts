import { DashboardApiError, dashboardRequest } from "./dashboardApi.js";
import { dashboardFallbackMessage } from "./dashboardFallback.js";
import { markProtectedDashboardReady, runDashboardLogout } from "./dashboardSessionFlow.js";
import { logoutDashboardSession } from "./session.js";
import {
  buildExternalApiOrigin,
  buildLanApiOrigin,
  renderStatusPlan,
  type DashboardStatus,
  type StatusExtensionSetupPlan
} from "./statusPageModel.js";

type StatusValue = "healthy" | "degraded" | "unhealthy" | "unknown";

const root = document.querySelector<HTMLDivElement>("#status-app");

if (!root) {
  throw new Error("Status root element is missing.");
}

const appRoot = root;

function appendText(parent: HTMLElement, tagName: keyof HTMLElementTagNameMap, text: string): HTMLElement {
  const element = document.createElement(tagName);
  element.textContent = text;
  parent.append(element);
  return element;
}

function statusLabel(value: StatusValue): string {
  if (value === "healthy") return "정상";
  if (value === "degraded") return "주의";
  if (value === "unhealthy") return "비정상";
  return "알 수 없음";
}

function formatLastChecked(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "알 수 없음";
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

function badge(value: StatusValue): HTMLElement {
  const element = document.createElement("span");
  element.className = `health-badge ${value}`;
  element.textContent = statusLabel(value);
  return element;
}

function renderHeader(): HTMLElement {
  const header = document.createElement("header");
  header.className = "admin-header";

  const copy = document.createElement("div");
  appendText(copy, "p", "OASecure 서버 상태").className = "eyebrow";
  appendText(copy, "h1", "서버 상태");
  appendText(copy, "p", "API, PostgreSQL, 마이그레이션, 필터 규칙 상태를 확인합니다.").className = "header-desc";

  const nav = document.createElement("nav");
  nav.className = "header-actions";
  const overview = appendText(nav, "a", "대시보드") as HTMLAnchorElement;
  overview.href = "./overview.html";
  overview.className = "nav-button";
  const events = appendText(nav, "a", "이벤트 관리") as HTMLAnchorElement;
  events.href = "./events.html";
  events.className = "nav-button";
  const users = appendText(nav, "a", "사용자 관리") as HTMLAnchorElement;
  users.href = "./users.html";
  users.className = "nav-button";
  const filters = appendText(nav, "a", "필터 관리") as HTMLAnchorElement;
  filters.href = "./filters.html";
  filters.className = "nav-button";
  const status = appendText(nav, "a", "서버 상태") as HTMLAnchorElement;
  status.href = "./status.html";
  status.className = "nav-button active";
  const logout = appendText(nav, "a", "로그아웃") as HTMLAnchorElement;
  logout.href = "./login.html";
  logout.className = "logout-button";
  logout.addEventListener("click", (event) => {
    event.preventDefault();
    void logoutAndRedirect();
  });

  nav.append(overview, events, users, filters, status, logout);
  header.append(copy, nav);
  return header;
}

function renderShell(...children: HTMLElement[]): void {
  const main = document.createElement("main");
  main.className = "dashboard status-dashboard";
  main.append(...children);
  appRoot.replaceChildren(renderHeader(), main);
}

function dependencyCard(label: string, value: StatusValue): HTMLElement {
  const card = document.createElement("article");
  card.className = "dependency-card";
  const row = document.createElement("div");
  row.className = "dependency-card-header";
  appendText(row, "strong", label);
  row.append(badge(value));
  card.append(row);
  return card;
}

function renderExtensionSetup(plan: StatusExtensionSetupPlan): HTMLElement {
  const card = document.createElement("section");
  card.className = "status-summary-card extension-setup-card";
  const copy = document.createElement("div");
  appendText(copy, "p", "운영 안내").className = "eyebrow";
  appendText(copy, "h2", plan.title);
  appendText(copy, "p", plan.description).className = "status-summary-copy";

  const settings = document.createElement("div");
  settings.className = "status-setup-values";
  for (const item of plan.connectionCards) {
    const entry = document.createElement("article");
    entry.className = "status-setup-value-card";
    if (item.state) {
      entry.classList.add(`status-setup-value-${item.state}`);
    }
    appendText(entry, "span", item.label);
    appendText(entry, "strong", item.value);
    appendText(entry, "p", item.description);
    if (item.copyValue) {
      const copyButton = document.createElement("button");
      copyButton.className = "users-secondary-button status-copy-button";
      copyButton.type = "button";
      copyButton.textContent = "복사";
      copyButton.addEventListener("click", async () => {
        await navigator.clipboard.writeText(item.copyValue ?? "");
        copyButton.textContent = "복사됨";
      });
      entry.append(copyButton);
    }
    settings.append(entry);
  }

  const actions = document.createElement("div");
  actions.className = "status-setup-actions";
  const helpButton = document.createElement("button");
  helpButton.className = "users-primary-button status-help-button";
  helpButton.type = "button";
  helpButton.textContent = "API URL 확인 방법";
  helpButton.addEventListener("click", () => openExtensionSetupDialog(plan));
  actions.append(helpButton);

  card.append(copy, settings, actions);
  return card;
}

function openExtensionSetupDialog(plan: StatusExtensionSetupPlan): void {
  const existing = document.querySelector<HTMLDivElement>(".status-help-backdrop");
  existing?.remove();

  const backdrop = document.createElement("div");
  backdrop.className = "status-help-backdrop";

  const dialog = document.createElement("section");
  dialog.className = "status-help-dialog";
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  dialog.setAttribute("aria-labelledby", "status-help-title");

  const header = document.createElement("div");
  header.className = "status-help-header";
  const title = appendText(header, "h2", "API URL 확인 방법");
  title.id = "status-help-title";
  const close = document.createElement("button");
  close.className = "status-help-close";
  close.type = "button";
  close.textContent = "닫기";
  close.addEventListener("click", () => backdrop.remove());
  header.append(close);

  const list = document.createElement("ol");
  list.className = "status-setup-list";
  for (const section of plan.helpSections) {
    const sectionItem = document.createElement("li");
    appendText(sectionItem, "strong", section.title);
    const nested = document.createElement("ol");
    nested.className = "status-help-step-list";
    for (const step of section.steps) {
      appendText(nested, "li", step);
    }
    sectionItem.append(nested);
    list.append(sectionItem);
  }

  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) {
      backdrop.remove();
    }
  });

  dialog.append(header, renderApiUrlBuilder(plan), list);
  backdrop.append(dialog);
  document.body.append(backdrop);
  close.focus();
}

function renderReadonlyOutput(label: string): { root: HTMLElement; output: HTMLInputElement } {
  const root = document.createElement("label");
  root.className = "status-url-builder-output";
  appendText(root, "span", label);
  const output = document.createElement("input");
  output.readOnly = true;
  output.value = "값을 입력하면 API URL이 생성됩니다.";
  root.append(output);
  return { root, output };
}

function renderApiUrlBuilder(plan: StatusExtensionSetupPlan): HTMLElement {
  const builder = document.createElement("section");
  builder.className = "status-url-builder";
  appendText(builder, "h3", "API URL 만들기");
  appendText(builder, "p", "환경변수 없이 서버 PC 주소 또는 외부 주소를 입력하면 Chrome 확장프로그램에 넣을 API URL을 만듭니다.");

  const modeControls = document.createElement("div");
  modeControls.className = "status-url-builder-mode";
  const lanMode = document.createElement("button");
  lanMode.type = "button";
  lanMode.textContent = "내부망 주소 만들기";
  const externalMode = document.createElement("button");
  externalMode.type = "button";
  externalMode.textContent = "외부망 주소 만들기";
  modeControls.append(lanMode, externalMode);

  const lan = document.createElement("article");
  lan.className = "status-url-builder-panel";
  appendText(lan, "h4", "같은 사무실/공유기에서 사용");
  appendText(lan, "p", "서버 PC의 실제 IPv4 주소를 입력합니다. Docker 컨테이너 내부 주소는 사용하지 않습니다.");
  const lanLabel = document.createElement("label");
  appendText(lanLabel, "span", "서버 PC IPv4 주소");
  const lanInput = document.createElement("input");
  lanInput.placeholder = "예: 192.168.0.10";
  lanLabel.append(lanInput);
  const lanResult = renderReadonlyOutput("생성된 내부망 API URL");
  lan.append(lanLabel, lanResult.root);

  const external = document.createElement("article");
  external.className = "status-url-builder-panel";
  appendText(external, "h4", "외부/다른 네트워크에서 사용");
  appendText(external, "p", "포트포워딩이나 도메인 연결 후 외부에서 접속 가능한 주소와 외부 포트를 입력합니다.");
  const hostLabel = document.createElement("label");
  appendText(hostLabel, "span", "공인 IP 또는 도메인");
  const hostInput = document.createElement("input");
  hostInput.placeholder = "예: promptguard.example.com";
  hostLabel.append(hostInput);
  const portLabel = document.createElement("label");
  appendText(portLabel, "span", "외부 포트");
  const portInput = document.createElement("input");
  portInput.inputMode = "numeric";
  portInput.placeholder = plan.urlBuilder.apiPort;
  portInput.value = plan.urlBuilder.apiPort;
  portLabel.append(portInput);
  const httpsLabel = document.createElement("label");
  httpsLabel.className = "status-url-builder-check";
  const httpsInput = document.createElement("input");
  httpsInput.type = "checkbox";
  httpsLabel.append(httpsInput, document.createTextNode(" HTTPS 사용"));
  const externalResult = renderReadonlyOutput("생성된 외부 API URL");
  external.append(hostLabel, portLabel, httpsLabel, externalResult.root);

  let mode: "lan" | "external" = "lan";
  const renderMode = () => {
    lan.hidden = mode !== "lan";
    external.hidden = mode !== "external";
    lanMode.classList.toggle("active", mode === "lan");
    externalMode.classList.toggle("active", mode === "external");
  };
  lanMode.addEventListener("click", () => {
    mode = "lan";
    renderMode();
  });
  externalMode.addEventListener("click", () => {
    mode = "external";
    renderMode();
  });

  const updateLan = () => {
    lanResult.output.value = buildLanApiOrigin(lanInput.value, plan.urlBuilder.apiPort) ?? "서버 PC의 실제 IPv4 주소를 입력하세요.";
  };
  const updateExternal = () => {
    externalResult.output.value =
      buildExternalApiOrigin(hostInput.value, portInput.value, httpsInput.checked) ?? "공인 IP/도메인과 1-65535 포트를 입력하세요.";
  };
  lanInput.addEventListener("input", updateLan);
  hostInput.addEventListener("input", updateExternal);
  portInput.addEventListener("input", updateExternal);
  httpsInput.addEventListener("change", updateExternal);
  renderMode();
  updateLan();
  updateExternal();

  builder.append(modeControls, lan, external);
  if (plan.urlBuilder.excludedOrigins.length > 0) {
    const notice = document.createElement("p");
    notice.className = "status-url-builder-notice";
    notice.textContent = `컨테이너 내부 주소는 제외됨: ${plan.urlBuilder.excludedOrigins.join(", ")}`;
    builder.append(notice);
  }
  return builder;
}

function renderLoading(): void {
  const card = document.createElement("section");
  card.className = "status-summary-card";
  appendText(card, "p", dashboardFallbackMessage("loading"));
  renderShell(card);
}

function renderUnavailable(statusCode?: number): void {
  const card = document.createElement("section");
  card.className = "status-summary-card";
  const copy = document.createElement("div");
  appendText(copy, "p", "상태 확인 불가").className = "eyebrow";
  appendText(copy, "h2", statusCode === 401 || statusCode === 403 ? "로그인이 필요합니다" : "상태 확인 불가");
  appendText(copy, "p", dashboardFallbackMessage("error", statusCode)).className =
    "status-summary-copy";
  card.append(copy, badge("unknown"));
  renderShell(card);
}

function renderStatus(payload: DashboardStatus): void {
  const plan = renderStatusPlan(payload);
  const summary = document.createElement("section");
  summary.className = "status-summary-card";
  const copy = document.createElement("div");
  appendText(copy, "p", "서버 상태").className = "eyebrow";
  appendText(copy, "h2", statusLabel(payload.status));
  appendText(copy, "p", "대시보드에 표시 가능한 상태 메타데이터만 보여줍니다. 상세 설정값과 secret은 표시하지 않습니다.").className =
    "status-summary-copy";
  summary.append(copy, badge(payload.status));

  const meta = document.createElement("section");
  meta.className = "status-meta-grid";
  const lastChecked = document.createElement("article");
  lastChecked.className = "status-meta-card";
  appendText(lastChecked, "span", "마지막 확인");
  appendText(lastChecked, "strong", formatLastChecked(payload.last_checked));
  meta.append(lastChecked);

  const dependencies = document.createElement("section");
  dependencies.className = "dependency-grid";
  dependencies.append(
    dependencyCard("API 서버", payload.api_status),
    dependencyCard("PostgreSQL", payload.postgres_status),
    dependencyCard("마이그레이션", payload.migration_status),
    dependencyCard("필터 규칙", payload.filter_rules_status)
  );

  renderShell(summary, meta, dependencies, renderExtensionSetup(plan.extensionSetup));
  markProtectedDashboardReady(document.body);
}

async function fetchStatus(): Promise<void> {
  renderLoading();
  try {
    renderStatus(await dashboardRequest<DashboardStatus>("/dashboard/status"));
  } catch (error) {
    renderUnavailable(error instanceof DashboardApiError ? error.status : undefined);
  }
}

async function logoutAndRedirect(): Promise<void> {
  await runDashboardLogout({
    logout: logoutDashboardSession,
    redirectToLogin: () => {
      window.location.href = "./login.html";
    },
    showError: () => renderUnavailable(403),
  });
}

void fetchStatus();

export {};
