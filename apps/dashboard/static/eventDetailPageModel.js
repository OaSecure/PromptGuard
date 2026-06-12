import { dashboardFallbackMessage } from "./dashboardFallback.js";
function formatDateTime(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime()))
        return "-";
    const year = date.getUTCFullYear();
    const month = `${date.getUTCMonth() + 1}`.padStart(2, "0");
    const day = `${date.getUTCDate()}`.padStart(2, "0");
    const hours = `${date.getUTCHours()}`.padStart(2, "0");
    const minutes = `${date.getUTCMinutes()}`.padStart(2, "0");
    return `${year}-${month}-${day} ${hours}:${minutes}`;
}
export function parseEventIdFromLocationSearch(search) {
    const params = new URLSearchParams(search);
    const eventId = params.get("event_id")?.trim();
    return eventId ? eventId : null;
}
export function projectEventDetailSummary(detail) {
    return {
        eventId: detail.event_id,
        createdAt: formatDateTime(detail.created_at),
        username: detail.username,
        service: detail.service ?? "-",
        platform: detail.platform ?? "-",
        action: detail.action,
        riskScore: String(detail.risk_score),
        riskLevel: detail.risk_level,
        detectionCount: String(detail.detection_count),
        inputCount: String(detail.input_count),
        contentUnavailableCount: String(detail.content_unavailable_count),
    };
}
export function projectDetectionRows(rows) {
    return rows.map((row) => ({
        category: row.category,
        type: row.type,
        source: row.source,
        severity: row.severity,
        action: row.action ?? "-",
        reasonCode: row.reason_code,
        matchCount: String(row.match_count),
    }));
}
export function projectInputRows(rows) {
    return rows.map((row) => ({
        inputId: row.input_id,
        inputIndex: String(row.input_index),
        kind: row.kind,
        source: row.source,
        decisionBasis: row.decision_basis,
        contentUnavailableReason: row.content_unavailable_reason ?? "-",
        limitExceeded: row.limit_exceeded ?? "-",
    }));
}
export function projectBusinessContextRows(rows) {
    return rows.map((row) => ({
        source: row.source ?? "-",
        reasonCode: row.reason_code,
        matchCount: String(row.match_count),
        matchedKeywords: row.matched_keywords.join(", ") || "-",
        evidenceCounts: Object.entries(row.evidence_counts)
            .map(([key, value]) => `${key}: ${value}`)
            .join(", ") || "-",
    }));
}
export function deriveEventDetailScreenState(phase, hasDetail) {
    if (phase === "loading") {
        return { kind: "loading", message: dashboardFallbackMessage("loading") };
    }
    if (phase === "error") {
        return { kind: "error", message: dashboardFallbackMessage("error") };
    }
    if (!hasDetail) {
        return { kind: "empty", message: dashboardFallbackMessage("empty") };
    }
    return { kind: "ready", message: "" };
}
export function safeEventDetailErrorMessage(status) {
    return dashboardFallbackMessage("error", status);
}
