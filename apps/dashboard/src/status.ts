import "./styles/main.css";

type StatusValue = "healthy" | "degraded" | "unhealthy" | "disabled" | "unknown";

type DependencyStatus = {
  status: StatusValue;
};

type DashboardStatus = {
  status: StatusValue;
  last_checked: string;
  api: DependencyStatus;
  postgres: DependencyStatus;
  migrations: DependencyStatus;
  filter_rules: DependencyStatus;
};

const app = document.querySelector<HTMLDivElement>("#status-app");
const apiBaseUrl = (import.meta.env.VITE_PROMPTGUARD_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

if (!app) {
  throw new Error("Status root element is missing.");
}

const appRoot = app;

function appendText(parent: HTMLElement, tagName: keyof HTMLElementTagNameMap, text: string): HTMLElement {
  const element = document.createElement(tagName);
  element.textContent = text;
  parent.append(element);
  return element;
}

function statusLabel(value: StatusValue): string {
  if (value === "healthy") return "Healthy";
  if (value === "degraded") return "Degraded";
  if (value === "unhealthy") return "Unhealthy";
  if (value === "disabled") return "Disabled";
  return "Unknown";
}

function formatCheckedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not checked";
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

function header(): HTMLElement {
  const section = document.createElement("header");
  section.className = "admin-header";

  const copy = document.createElement("div");
  appendText(copy, "p", "PromptGuard Dashboard").className = "eyebrow";
  appendText(copy, "h1", "Server Status");
  appendText(copy, "p", "API, PostgreSQL, migration, filter rule 상태만 표시합니다.").className = "header-desc";

  const nav = document.createElement("nav");
  nav.className = "header-actions";
  const overview = appendText(nav, "a", "Overview") as HTMLAnchorElement;
  overview.href = "./index.html#admin";
  overview.className = "nav-button";
  const filters = appendText(nav, "a", "Filters") as HTMLAnchorElement;
  filters.href = "./index.html#filters";
  filters.className = "nav-button";

  section.append(copy, nav);
  return section;
}

function card(label: string, status: StatusValue): HTMLElement {
  const element = document.createElement("article");
  element.className = "dependency-card";
  const top = document.createElement("div");
  top.className = "dependency-card-header";
  appendText(top, "strong", label);
  top.append(badge(status));
  element.append(top);
  return element;
}

function renderLoading(): void {
  const main = document.createElement("main");
  main.className = "dashboard status-dashboard";
  const loading = document.createElement("section");
  loading.className = "status-summary-card";
  appendText(loading, "p", "Loading status metadata...");
  main.append(loading);
  appRoot.replaceChildren(header(), main);
}

function renderError(statusCode?: number): void {
  const main = document.createElement("main");
  main.className = "dashboard status-dashboard";
  const panel = document.createElement("section");
  panel.className = "status-summary-card";
  const copy = document.createElement("div");
  appendText(copy, "p", "Status Unavailable").className = "eyebrow";
  appendText(copy, "h2", statusCode === 401 || statusCode === 403 ? "Authentication Required" : "Unknown");
  appendText(copy, "p", "Status metadata could not be loaded safely. Sign in with an ADMIN dashboard session and try again.").className = "status-summary-copy";
  panel.append(copy, badge("unknown"));
  main.append(panel);
  appRoot.replaceChildren(header(), main);
}

function renderStatus(payload: DashboardStatus): void {
  const main = document.createElement("main");
  main.className = "dashboard status-dashboard";

  const summary = document.createElement("section");
  summary.className = "status-summary-card";
  const copy = document.createElement("div");
  appendText(copy, "p", "Server Status").className = "eyebrow";
  appendText(copy, "h2", statusLabel(payload.status));
  appendText(copy, "p", "Dashboard-safe status summary. Detailed configuration values are not displayed.").className = "status-summary-copy";
  summary.append(copy, badge(payload.status));

  const meta = document.createElement("section");
  meta.className = "status-meta-grid";
  const lastChecked = document.createElement("article");
  lastChecked.className = "status-meta-card";
  appendText(lastChecked, "span", "Last Checked");
  appendText(lastChecked, "strong", formatCheckedAt(payload.last_checked));
  meta.append(lastChecked);

  const dependencies = document.createElement("section");
  dependencies.className = "dependency-grid";
  dependencies.append(
    card("API", payload.api.status),
    card("PostgreSQL", payload.postgres.status),
    card("Migration", payload.migrations.status),
    card("Filter Rules", payload.filter_rules.status)
  );

  main.append(summary, meta, dependencies);
  appRoot.replaceChildren(header(), main);
}

async function fetchStatus(): Promise<void> {
  renderLoading();
  try {
    const response = await fetch(`${apiBaseUrl}/dashboard/status`, {
      credentials: "include",
      headers: {
        Accept: "application/json"
      }
    });
    if (!response.ok) {
      renderError(response.status);
      return;
    }
    renderStatus((await response.json()) as DashboardStatus);
  } catch {
    renderError();
  }
}

void fetchStatus();
