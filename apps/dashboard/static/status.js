const root = document.querySelector("#status-app");
const apiBaseUrl = document.documentElement.dataset.promptguardApiBaseUrl ?? "http://localhost:8000";
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
        return "Healthy";
    if (value === "degraded")
        return "Degraded";
    if (value === "unhealthy")
        return "Unhealthy";
    return "Unknown";
}
function formatLastChecked(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime()))
        return "Unknown";
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
    appendText(copy, "p", "PromptGuard Dashboard").className = "eyebrow";
    appendText(copy, "h1", "Server Status");
    appendText(copy, "p", "API, PostgreSQL, migration, and filter rule readiness.").className = "header-desc";
    const nav = document.createElement("nav");
    nav.className = "header-actions";
    const admin = appendText(nav, "a", "Admin");
    admin.href = "./admin.html";
    admin.className = "nav-button";
    const filters = appendText(nav, "a", "Filters");
    filters.href = "./filters.html";
    filters.className = "nav-button";
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
function renderLoading() {
    const card = document.createElement("section");
    card.className = "status-summary-card";
    appendText(card, "p", "Loading status metadata...");
    renderShell(card);
}
function renderUnavailable(statusCode) {
    const card = document.createElement("section");
    card.className = "status-summary-card";
    const copy = document.createElement("div");
    appendText(copy, "p", "Status Unavailable").className = "eyebrow";
    appendText(copy, "h2", statusCode === 401 || statusCode === 403 ? "Authentication Required" : "Unknown");
    appendText(copy, "p", "Status metadata could not be loaded safely. Use an ADMIN dashboard session and try again.").className =
        "status-summary-copy";
    card.append(copy, badge("unknown"));
    renderShell(card);
}
function renderStatus(payload) {
    const summary = document.createElement("section");
    summary.className = "status-summary-card";
    const copy = document.createElement("div");
    appendText(copy, "p", "Server Status").className = "eyebrow";
    appendText(copy, "h2", statusLabel(payload.status));
    appendText(copy, "p", "Dashboard-safe status summary. Detailed configuration values are not displayed.").className =
        "status-summary-copy";
    summary.append(copy, badge(payload.status));
    const meta = document.createElement("section");
    meta.className = "status-meta-grid";
    const lastChecked = document.createElement("article");
    lastChecked.className = "status-meta-card";
    appendText(lastChecked, "span", "Last Checked");
    appendText(lastChecked, "strong", formatLastChecked(payload.last_checked));
    meta.append(lastChecked);
    const dependencies = document.createElement("section");
    dependencies.className = "dependency-grid";
    dependencies.append(dependencyCard("API", payload.api_status), dependencyCard("PostgreSQL", payload.postgres_status), dependencyCard("Migration", payload.migration_status), dependencyCard("Filter Rules", payload.filter_rules_status));
    renderShell(summary, meta, dependencies);
}
async function fetchStatus() {
    renderLoading();
    try {
        const response = await fetch(`${apiBaseUrl}/dashboard/status`, {
            credentials: "include",
            headers: {
                Accept: "application/json"
            }
        });
        if (!response.ok) {
            renderUnavailable(response.status);
            return;
        }
        renderStatus((await response.json()));
    }
    catch {
        renderUnavailable();
    }
}
void fetchStatus();
export {};
