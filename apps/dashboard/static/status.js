import { DashboardApiError, dashboardRequest } from "./dashboardApi.js";
import { dashboardFallbackMessage } from "./dashboardFallback.js";
import { markProtectedDashboardReady, runDashboardLogout } from "./dashboardSessionFlow.js";
import { logoutDashboardSession } from "./session.js";
import { renderStatusPlan } from "./statusPageModel.js";
const root = document.querySelector("#status-app");
if (!root) {
    throw new Error("Status root element is missing.");
}
const appRoot = root;
function appendText(parent, tagName, text) {
    const element = document.createElement(tagName);
    element.textContent = text;
    parent.append(element);
    return element;
}
function statusLabel(value) {
    if (value === "healthy")
        return "정상";
    if (value === "degraded")
        return "주의";
    if (value === "unhealthy")
        return "비정상";
    return "알 수 없음";
}
function formatLastChecked(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime()))
        return "알 수 없음";
    return new Intl.DateTimeFormat("ko-KR", {
        dateStyle: "medium",
        timeStyle: "short"
    }).format(date);
}
function badge(value) {
    const element = document.createElement("span");
    element.className = `health-badge ${value}`;
    element.textContent = statusLabel(value);
    return element;
}
function renderHeader() {
    const header = document.createElement("header");
    header.className = "admin-header";
    const copy = document.createElement("div");
    appendText(copy, "p", "OASecure 서버 상태").className = "eyebrow";
    appendText(copy, "h1", "서버 상태");
    appendText(copy, "p", "API, PostgreSQL, 마이그레이션, 필터 규칙 상태를 확인합니다.").className = "header-desc";
    const nav = document.createElement("nav");
    nav.className = "header-actions";
    const overview = appendText(nav, "a", "대시보드");
    overview.href = "./overview.html";
    overview.className = "nav-button";
    const events = appendText(nav, "a", "이벤트 관리");
    events.href = "./events.html";
    events.className = "nav-button";
    const users = appendText(nav, "a", "사용자 관리");
    users.href = "./users.html";
    users.className = "nav-button";
    const filters = appendText(nav, "a", "필터 관리");
    filters.href = "./filters.html";
    filters.className = "nav-button";
    const status = appendText(nav, "a", "서버 상태");
    status.href = "./status.html";
    status.className = "nav-button active";
    const logout = appendText(nav, "a", "로그아웃");
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
function renderShell(...children) {
    const main = document.createElement("main");
    main.className = "dashboard status-dashboard";
    main.append(...children);
    appRoot.replaceChildren(renderHeader(), main);
}
function dependencyCard(label, value) {
    const card = document.createElement("article");
    card.className = "dependency-card";
    const row = document.createElement("div");
    row.className = "dependency-card-header";
    appendText(row, "strong", label);
    row.append(badge(value));
    card.append(row);
    return card;
}
function renderExtensionSetup(plan) {
    const card = document.createElement("section");
    card.className = "status-summary-card extension-setup-card";
    const copy = document.createElement("div");
    appendText(copy, "p", "운영 안내").className = "eyebrow";
    appendText(copy, "h2", plan.title);
    appendText(copy, "p", plan.description).className = "status-summary-copy";
    const settings = document.createElement("div");
    settings.className = "status-setup-values";
    for (const item of plan.settings) {
        const entry = document.createElement("article");
        entry.className = "status-setup-value-card";
        appendText(entry, "span", item.label);
        appendText(entry, "strong", item.value);
        appendText(entry, "p", item.description);
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
function openExtensionSetupDialog(plan) {
    const existing = document.querySelector(".status-help-backdrop");
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
    for (const step of plan.steps) {
        appendText(list, "li", step);
    }
    backdrop.addEventListener("click", (event) => {
        if (event.target === backdrop) {
            backdrop.remove();
        }
    });
    dialog.append(header, list);
    backdrop.append(dialog);
    document.body.append(backdrop);
    close.focus();
}
function renderLoading() {
    const card = document.createElement("section");
    card.className = "status-summary-card";
    appendText(card, "p", dashboardFallbackMessage("loading"));
    renderShell(card);
}
function renderUnavailable(statusCode) {
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
function renderStatus(payload) {
    const plan = renderStatusPlan(payload, window.location.origin);
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
    dependencies.append(dependencyCard("API 서버", payload.api_status), dependencyCard("PostgreSQL", payload.postgres_status), dependencyCard("마이그레이션", payload.migration_status), dependencyCard("필터 규칙", payload.filter_rules_status));
    renderShell(summary, meta, dependencies, renderExtensionSetup(plan.extensionSetup));
    markProtectedDashboardReady(document.body);
}
async function fetchStatus() {
    renderLoading();
    try {
        renderStatus(await dashboardRequest("/dashboard/status"));
    }
    catch (error) {
        renderUnavailable(error instanceof DashboardApiError ? error.status : undefined);
    }
}
async function logoutAndRedirect() {
    await runDashboardLogout({
        logout: logoutDashboardSession,
        redirectToLogin: () => {
            window.location.href = "./login.html";
        },
        showError: () => renderUnavailable(403),
    });
}
void fetchStatus();
