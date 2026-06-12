import { dashboardFallbackMessage } from "./dashboardFallback.js";

export type DashboardDetectionSummary = {
  category: string;
  type: string;
  count: number;
};

export type DashboardDetectionRow = {
  category: string;
  type: string;
  input_id: string | null;
  input_index: number | null;
  kind: string | null;
  source: string;
  rule_id: string | null;
  detector_id: string | null;
  severity: string;
  action: string | null;
  placeholder: string | null;
  reason_code: string;
  match_count: number;
};

export type DashboardInputRow = {
  input_id: string;
  input_index: number;
  kind: string;
  source: string;
  content_included: boolean;
  content_scanned: boolean;
  decision_basis: string;
  content_unavailable_reason: string | null;
  limit_exceeded: string | null;
};

export type DashboardBusinessContextMatch = {
  input_id: string | null;
  input_index: number | null;
  kind: string | null;
  source: string | null;
  category: string;
  reason_code: string;
  match_count: number;
  matched_keywords: string[];
  evidence_counts: Record<string, number>;
};

export type DashboardEventDetail = {
  event_id: string;
  created_at: string;
  login_id: string;
  username: string;
  service: string | null;
  platform: string | null;
  action: string;
  risk_score: number;
  risk_level: string;
  primary_detection_category: string | null;
  primary_detection_type: string | null;
  detection_count: number;
  input_count: number;
  content_unavailable_count: number;
  detail_available: boolean;
  detection_summary: DashboardDetectionSummary[];
  detections: DashboardDetectionRow[];
  input_results: DashboardInputRow[];
  content_unavailable_inputs: DashboardInputRow[];
  business_context_matches: DashboardBusinessContextMatch[];
};

export type EventDetailScreenState = {
  kind: "loading" | "empty" | "error" | "ready";
  message: string;
};

export type EventDetailSummaryView = {
  eventId: string;
  createdAt: string;
  username: string;
  service: string;
  platform: string;
  action: string;
  riskScore: string;
  riskLevel: string;
  detectionCount: string;
  inputCount: string;
  contentUnavailableCount: string;
};

export type DetectionRowView = {
  category: string;
  type: string;
  source: string;
  severity: string;
  action: string;
  reasonCode: string;
  matchCount: string;
};

export type InputRowView = {
  inputId: string;
  inputIndex: string;
  kind: string;
  source: string;
  decisionBasis: string;
  contentUnavailableReason: string;
  limitExceeded: string;
};

export type BusinessContextRowView = {
  source: string;
  reasonCode: string;
  matchCount: string;
  matchedKeywords: string;
  evidenceCounts: string;
};

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const year = date.getUTCFullYear();
  const month = `${date.getUTCMonth() + 1}`.padStart(2, "0");
  const day = `${date.getUTCDate()}`.padStart(2, "0");
  const hours = `${date.getUTCHours()}`.padStart(2, "0");
  const minutes = `${date.getUTCMinutes()}`.padStart(2, "0");
  return `${year}-${month}-${day} ${hours}:${minutes}`;
}

export function parseEventIdFromLocationSearch(search: string): string | null {
  const params = new URLSearchParams(search);
  const eventId = params.get("event_id")?.trim();
  return eventId ? eventId : null;
}

export function projectEventDetailSummary(detail: DashboardEventDetail): EventDetailSummaryView {
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

export function projectDetectionRows(rows: DashboardDetectionRow[]): DetectionRowView[] {
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

export function projectInputRows(rows: DashboardInputRow[]): InputRowView[] {
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

export function projectBusinessContextRows(rows: DashboardBusinessContextMatch[]): BusinessContextRowView[] {
  return rows.map((row) => ({
    source: row.source ?? "-",
    reasonCode: row.reason_code,
    matchCount: String(row.match_count),
    matchedKeywords: row.matched_keywords.join(", ") || "-",
    evidenceCounts:
      Object.entries(row.evidence_counts)
        .map(([key, value]) => `${key}: ${value}`)
        .join(", ") || "-",
  }));
}

export function deriveEventDetailScreenState(
  phase: "loading" | "ready" | "error",
  hasDetail: boolean,
): EventDetailScreenState {
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

export function safeEventDetailErrorMessage(status: number): string {
  return dashboardFallbackMessage("error", status);
}
