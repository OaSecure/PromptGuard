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
export function buildEventDetailHref(eventId) {
    return `./event-detail.html?event_id=${encodeURIComponent(eventId)}`;
}
export function projectEventTableRows(events) {
    return events.map((event) => ({
        eventId: event.event_id,
        detailHref: buildEventDetailHref(event.event_id),
        cells: [
            { key: "created_at", text: formatDateTime(event.created_at), tone: "plain" },
            { key: "username", text: event.username, tone: "plain" },
            { key: "service", text: event.service ?? "-", tone: "plain" },
            { key: "action", text: event.action, tone: "action" },
            { key: "risk_level", text: event.risk_level, tone: "risk" },
            { key: "primary_detection_category", text: event.primary_detection_category ?? "-", tone: "plain" },
            { key: "primary_detection_type", text: event.primary_detection_type ?? "-", tone: "plain" },
            { key: "detection_count", text: String(event.detection_count), tone: "count" },
            { key: "input_count", text: String(event.input_count), tone: "count" },
            { key: "content_unavailable_count", text: String(event.content_unavailable_count), tone: "count" },
            { key: "detail", text: "상세보기", tone: "plain" },
        ],
    }));
}
export function deriveEventsScreenState(phase, rowCount) {
    if (phase === "loading") {
        return { kind: "loading", message: dashboardFallbackMessage("loading") };
    }
    if (phase === "error") {
        return { kind: "error", message: dashboardFallbackMessage("error") };
    }
    if (rowCount === 0) {
        return { kind: "empty", message: dashboardFallbackMessage("empty") };
    }
    return { kind: "ready", message: "" };
}
export function safeEventsErrorMessage(status) {
    return dashboardFallbackMessage("error", status);
}
