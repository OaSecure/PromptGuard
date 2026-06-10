import { DashboardApiError, dashboardRequest } from "./dashboardApi.js";
import { logoutDashboardSession } from "./session.js";
import { deriveEventDetailScreenState, parseEventIdFromLocationSearch, projectBusinessContextRows, projectDetectionRows, projectEventDetailSummary, projectInputRows, safeEventDetailErrorMessage, } from "./eventDetailPageModel.js";
const detailTitle = requireElement("detail-title");
const detailMessage = requireElement("detail-message");
const summaryGrid = requireElement("detail-summary-grid");
const detectionSummaryBody = requireElement("detection-summary-body");
const detectionsBody = requireElement("detections-body");
const inputsBody = requireElement("inputs-body");
const unavailableInputsBody = requireElement("unavailable-inputs-body");
const businessContextBody = requireElement("business-context-body");
function requireElement(id) {
    const element = document.getElementById(id);
    if (!element) {
        throw new Error(`Missing event detail element: ${id}`);
    }
    return element;
}
function redirectToLogin() {
    window.location.href = "./login.html";
}
function setMessage(kind, text) {
    detailMessage.textContent = text;
    detailMessage.hidden = kind === "ready";
    detailMessage.setAttribute("role", kind === "error" ? "alert" : "status");
    detailMessage.setAttribute("aria-live", kind === "error" ? "assertive" : "polite");
}
function appendKeyValue(container, labelText, valueText) {
    const wrapper = document.createElement("div");
    const label = document.createElement("span");
    const value = document.createElement("strong");
    label.textContent = labelText;
    value.textContent = valueText;
    wrapper.append(label, value);
    container.append(wrapper);
}
function renderTableRow(values) {
    const tr = document.createElement("tr");
    values.forEach((value) => {
        const td = document.createElement("td");
        td.textContent = value;
        tr.append(td);
    });
    return tr;
}
function renderEmptyRow(columns, message) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = columns;
    td.textContent = message;
    tr.append(td);
    return tr;
}
function renderDetail(detail) {
    const summary = projectEventDetailSummary(detail);
    detailTitle.textContent = `이벤트 상세보기 · ${summary.eventId}`;
    summaryGrid.replaceChildren();
    appendKeyValue(summaryGrid, "이벤트 ID", summary.eventId);
    appendKeyValue(summaryGrid, "시간", summary.createdAt);
    appendKeyValue(summaryGrid, "사용자", summary.username);
    appendKeyValue(summaryGrid, "서비스", summary.service);
    appendKeyValue(summaryGrid, "플랫폼", summary.platform);
    appendKeyValue(summaryGrid, "Action", summary.action);
    appendKeyValue(summaryGrid, "위험도 점수", summary.riskScore);
    appendKeyValue(summaryGrid, "위험도", summary.riskLevel);
    appendKeyValue(summaryGrid, "탐지 개수", summary.detectionCount);
    appendKeyValue(summaryGrid, "입력 개수", summary.inputCount);
    appendKeyValue(summaryGrid, "Content unavailable", summary.contentUnavailableCount);
    detectionSummaryBody.replaceChildren(...(detail.detection_summary.length > 0
        ? detail.detection_summary.map((item) => renderTableRow([item.category, item.type, String(item.count)]))
        : [renderEmptyRow(3, "탐지 요약이 없습니다.")]));
    const detections = projectDetectionRows(detail.detections);
    detectionsBody.replaceChildren(...(detections.length > 0
        ? detections.map((row) => renderTableRow([row.category, row.type, row.source, row.severity, row.action, row.reasonCode, row.matchCount]))
        : [renderEmptyRow(7, "탐지 항목이 없습니다.")]));
    const inputs = projectInputRows(detail.input_results);
    inputsBody.replaceChildren(...(inputs.length > 0
        ? inputs.map((row) => renderTableRow([row.inputId, row.inputIndex, row.kind, row.source, row.decisionBasis, row.contentUnavailableReason, row.limitExceeded]))
        : [renderEmptyRow(7, "입력 결과가 없습니다.")]));
    const unavailableInputs = projectInputRows(detail.content_unavailable_inputs);
    unavailableInputsBody.replaceChildren(...(unavailableInputs.length > 0
        ? unavailableInputs.map((row) => renderTableRow([row.inputId, row.inputIndex, row.kind, row.source, row.decisionBasis, row.contentUnavailableReason, row.limitExceeded]))
        : [renderEmptyRow(7, "Content unavailable 입력이 없습니다.")]));
    const businessContextRows = projectBusinessContextRows(detail.business_context_matches);
    businessContextBody.replaceChildren(...(businessContextRows.length > 0
        ? businessContextRows.map((row) => renderTableRow([row.source, row.reasonCode, row.matchCount, row.matchedKeywords, row.evidenceCounts]))
        : [renderEmptyRow(5, "Business Context metadata가 없습니다.")]));
}
async function loadEventDetail() {
    const eventId = parseEventIdFromLocationSearch(window.location.search);
    if (!eventId) {
        const state = deriveEventDetailScreenState("error", false);
        setMessage(state.kind, "이벤트 ID가 필요합니다.");
        return;
    }
    const loadingState = deriveEventDetailScreenState("loading", false);
    setMessage(loadingState.kind, loadingState.message);
    try {
        const detail = await dashboardRequest(`/dashboard/events/${encodeURIComponent(eventId)}`);
        renderDetail(detail);
        const state = deriveEventDetailScreenState("ready", true);
        setMessage(state.kind, state.message);
    }
    catch (error) {
        const status = error instanceof DashboardApiError ? error.status : 500;
        const state = deriveEventDetailScreenState("error", false);
        setMessage(state.kind, safeEventDetailErrorMessage(status));
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
void loadEventDetail();
