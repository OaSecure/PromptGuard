import { DashboardApiError, dashboardRequest } from "./dashboardApi.js";
import { logoutDashboardSession } from "./session.js";
const message = requireElement("overview-message");
const cards = requireElement("overview-cards");
const periodLabel = requireElement("overview-period");
const actionCounts = requireElement("action-counts");
const riskLevelCounts = requireElement("risk-level-counts");
const detectorCategoryCounts = requireElement("detector-category-counts");
const periodBuckets = requireElement("period-buckets");
const valueTargets = new Map(Array.from(document.querySelectorAll("[data-overview-value]")).map((element) => [
    element.dataset.overviewValue ?? "",
    element,
]));
function requireElement(id) {
    const element = document.getElementById(id);
    if (!element) {
        throw new Error(`Missing dashboard element: ${id}`);
    }
    return element;
}
function setMessage(text, kind) {
    message.textContent = text;
    message.hidden = kind === "ready";
    message.setAttribute("role", kind === "error" ? "alert" : "status");
    message.setAttribute("aria-live", kind === "error" ? "assertive" : "polite");
}
function setMetric(key, value) {
    const target = valueTargets.get(key);
    if (target) {
        target.textContent = value;
    }
}
function formatNumber(value) {
    return new Intl.NumberFormat("ko-KR").format(value);
}
function formatDateTime(value) {
    if (!value)
        return "없음";
    const date = new Date(value);
    if (Number.isNaN(date.getTime()))
        return "없음";
    return new Intl.DateTimeFormat("ko-KR", {
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    }).format(date);
}
function formatPeriodDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime()))
        return "-";
    return new Intl.DateTimeFormat("ko-KR", { month: "short", day: "2-digit" }).format(date);
}
function barClassForAction(action) {
    if (action === "block")
        return "blocked";
    if (action === "mask")
        return "masked";
    if (action === "warn")
        return "warned";
    return "";
}
function formatActionLabel(action) {
    if (action === "allow")
        return "허용";
    if (action === "block")
        return "차단";
    if (action === "mask")
        return "마스킹";
    if (action === "warn")
        return "경고";
    return action;
}
function renderActionCounts(rows) {
    const maxCount = Math.max(1, ...rows.map((row) => row.count));
    actionCounts.replaceChildren(...rows.map((row) => {
        const item = document.createElement("div");
        item.className = "bar-row";
        const label = document.createElement("span");
        label.textContent = formatActionLabel(row.action);
        const track = document.createElement("div");
        track.className = "bar-track";
        const fill = document.createElement("i");
        fill.className = `bar-fill ${barClassForAction(row.action)}`.trim();
        fill.style.width = `${Math.max(4, Math.round((row.count / maxCount) * 100))}%`;
        track.append(fill);
        const value = document.createElement("strong");
        value.textContent = formatNumber(row.count);
        item.append(label, track, value);
        return item;
    }));
}
function renderList(container, rows, key, emptyText) {
    if (rows.length === 0) {
        const empty = document.createElement("li");
        empty.textContent = emptyText;
        container.replaceChildren(empty);
        return;
    }
    container.replaceChildren(...rows.map((row, index) => {
        const item = document.createElement("li");
        item.style.setProperty("--slice-color", ["#2f80ed", "#27ae60", "#f2994a", "#9b51e0"][index % 4]);
        const label = document.createElement("span");
        label.textContent = row[key];
        const value = document.createElement("strong");
        value.textContent = formatNumber(row.count);
        item.append(label, value);
        return item;
    }));
}
function renderPeriodBuckets(rows) {
    if (rows.length === 0) {
        const empty = document.createElement("div");
        empty.className = "empty-state";
        empty.textContent = "기간별 데이터가 없습니다.";
        periodBuckets.replaceChildren(empty);
        return;
    }
    const visibleRows = rows.slice(-14);
    const maxCount = Math.max(1, ...visibleRows.map((row) => row.event_count));
    periodBuckets.replaceChildren(...visibleRows.map((row) => {
        const item = document.createElement("div");
        item.className = "period-column";
        item.title = [
            `전체: ${row.event_count}`,
            `차단: ${row.blocked_count}`,
            `마스킹: ${row.masked_count}`,
            `경고: ${row.warned_count}`,
        ].join(" | ");
        const value = document.createElement("strong");
        value.textContent = formatNumber(row.event_count);
        const bar = document.createElement("i");
        bar.style.height = `${Math.max(6, Math.round((row.event_count / maxCount) * 100))}%`;
        const label = document.createElement("span");
        label.textContent = formatPeriodDate(row.bucket_start);
        item.append(value, bar, label);
        return item;
    }));
}
function renderOverview(data) {
    setMetric("event_count", formatNumber(data.event_count));
    setMetric("blocked_count", formatNumber(data.blocked_count));
    setMetric("masked_count", formatNumber(data.masked_count));
    setMetric("warned_count", formatNumber(data.warned_count));
    setMetric("active_user_count", formatNumber(data.active_user_count));
    setMetric("content_unavailable_event_count", formatNumber(data.content_unavailable_event_count));
    setMetric("last_event_at", formatDateTime(data.last_event_at));
    periodLabel.textContent = `${formatPeriodDate(data.period_start)} - ${formatPeriodDate(data.period_end)}`;
    renderActionCounts(data.action_counts);
    renderList(riskLevelCounts, data.risk_level_counts, "risk_level", "위험도 데이터가 없습니다.");
    renderList(detectorCategoryCounts, data.detector_category_counts, "category", "탐지 카테고리 데이터가 없습니다.");
    renderPeriodBuckets(data.period_buckets);
    cards.setAttribute("aria-busy", "false");
    if (data.event_count === 0) {
        setMessage("현재 조회 기간에 표시할 이벤트가 없습니다.", "empty");
    }
    else {
        setMessage("", "ready");
    }
}
function redirectToLogin() {
    window.location.href = "./login.html";
}
function safeOverviewErrorMessage(error) {
    if (error instanceof DashboardApiError) {
        if (error.status === 401 || error.status === 403)
            return "대시보드 로그인이 필요합니다.";
        if (error.status === 0)
            return "대시보드 API에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
    }
    return "대시보드 요약을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
}
async function loadOverview() {
    cards.setAttribute("aria-busy", "true");
    setMessage("대시보드 요약을 불러오는 중입니다.", "loading");
    try {
        const data = await dashboardRequest("/dashboard/overview");
        renderOverview(data);
    }
    catch (error) {
        cards.setAttribute("aria-busy", "false");
        setMessage(safeOverviewErrorMessage(error), "error");
        if (error instanceof DashboardApiError && (error.status === 401 || error.status === 403)) {
            window.setTimeout(redirectToLogin, 700);
        }
    }
}
document.querySelectorAll(".logout-button").forEach((link) => {
    link.addEventListener("click", async (event) => {
        event.preventDefault();
        try {
            await logoutDashboardSession();
        }
        finally {
            redirectToLogin();
        }
    });
});
void loadOverview();
