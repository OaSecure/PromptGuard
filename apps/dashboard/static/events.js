import { DashboardApiError, dashboardRequest } from "./dashboardApi.js";
import { logoutDashboardSession } from "./session.js";
import { deriveEventsScreenState, projectEventTableRows, safeEventsErrorMessage, } from "./eventsPageModel.js";
const eventsMessage = requireElement("events-message");
const eventsTableBody = requireElement("events-table-body");
function requireElement(id) {
    const element = document.getElementById(id);
    if (!element) {
        throw new Error(`Missing events dashboard element: ${id}`);
    }
    return element;
}
function redirectToLogin() {
    window.location.href = "./login.html";
}
function setMessage(kind, text) {
    eventsMessage.textContent = text;
    eventsMessage.hidden = kind === "ready";
    eventsMessage.setAttribute("role", kind === "error" ? "alert" : "status");
    eventsMessage.setAttribute("aria-live", kind === "error" ? "assertive" : "polite");
}
function createBadge(text, className) {
    const badge = document.createElement("span");
    badge.className = className;
    badge.textContent = text;
    return badge;
}
function actionBadgeClass(action) {
    if (action === "BLOCK")
        return "status-badge result-blocked";
    if (action === "MASK")
        return "status-badge result-masked";
    if (action === "WARN")
        return "status-badge result-warned";
    return "status-badge";
}
function riskBadgeClass(riskLevel) {
    if (riskLevel === "critical")
        return "risk-badge risk-critical";
    if (riskLevel === "high")
        return "risk-badge risk-high";
    if (riskLevel === "medium")
        return "risk-badge risk-medium";
    return "risk-badge risk-low";
}
function renderEvents(events) {
    const rows = projectEventTableRows(events);
    eventsTableBody.replaceChildren(...rows.map((row) => {
        const tr = document.createElement("tr");
        row.cells.forEach((cell) => {
            const td = document.createElement("td");
            if (cell.key === "action") {
                td.append(createBadge(cell.text, actionBadgeClass(cell.text)));
            }
            else if (cell.key === "risk_level") {
                td.append(createBadge(cell.text, riskBadgeClass(cell.text)));
            }
            else if (cell.key === "primary_detection_type") {
                const link = document.createElement("a");
                link.href = row.detailHref;
                link.textContent = cell.text;
                td.append(link);
            }
            else {
                td.textContent = cell.text;
            }
            tr.append(td);
        });
        eventsTableBody.append(tr);
        return tr;
    }));
}
async function loadEvents() {
    const loadingState = deriveEventsScreenState("loading", 0);
    setMessage(loadingState.kind, loadingState.message);
    try {
        const events = await dashboardRequest("/dashboard/events");
        renderEvents(events);
        const state = deriveEventsScreenState("ready", events.length);
        setMessage(state.kind, state.message);
    }
    catch (error) {
        const status = error instanceof DashboardApiError ? error.status : 500;
        const state = deriveEventsScreenState("error", 0);
        setMessage(state.kind, safeEventsErrorMessage(status));
        if (status === 401 || status === 403) {
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
void loadEvents();
