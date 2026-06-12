import { DashboardApiError, dashboardRequest } from "./dashboardApi.js";
import { runDashboardLogout } from "./dashboardSessionFlow.js";
import { logoutDashboardSession } from "./session.js";

type StatusValue = "healthy" | "degraded" | "unhealthy" | "unknown";

type DashboardStatus = {
  status: StatusValue;
  last_checked: string;
  api_status: StatusValue;
  postgres_status: StatusValue;
  migration_status: StatusValue;
  filter_rules_status: StatusValue;
};

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
  const logout = appendText(nav, "a", "로그아웃") as HTMLAnchorElement;
  logout.href = "./login.html";
  logout.className = "logout-button";
  logout.addEventListener("click", (event) => {
    event.preventDefault();
    void logoutAndRedirect();
  });

  nav.append(overview, events, users, filters, logout);
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

function renderLoading(): void {
  const card = document.createElement("section");
  card.className = "status-summary-card";
  appendText(card, "p", "서버 상태 정보를 불러오는 중입니다.");
  renderShell(card);
}

function renderUnavailable(statusCode?: number): void {
  const card = document.createElement("section");
  card.className = "status-summary-card";
  const copy = document.createElement("div");
  appendText(copy, "p", "상태 확인 불가").className = "eyebrow";
  appendText(copy, "h2", statusCode === 401 || statusCode === 403 ? "로그인이 필요합니다" : "상태 확인 불가");
  appendText(copy, "p", "안전한 서버 상태 메타데이터를 불러오지 못했습니다. ADMIN 대시보드 세션으로 다시 시도해 주세요.").className =
    "status-summary-copy";
  card.append(copy, badge("unknown"));
  renderShell(card);
}

function renderStatus(payload: DashboardStatus): void {
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

  renderShell(summary, meta, dependencies);
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
