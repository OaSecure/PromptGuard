export type DashboardEventListItem = {
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
};

export type EventsScreenState = {
  kind: "loading" | "empty" | "error" | "ready";
  message: string;
};

export type EventTableCellTone = "action" | "risk" | "count" | "plain";

export type EventTableCell = {
  key:
    | "created_at"
    | "username"
    | "service"
    | "action"
    | "risk_level"
    | "primary_detection_category"
    | "primary_detection_type"
    | "detection_count"
    | "input_count"
    | "content_unavailable_count"
    | "detail";
  text: string;
  tone: EventTableCellTone;
};

export type EventTableRowView = {
  eventId: string;
  detailHref: string;
  cells: EventTableCell[];
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

export function buildEventDetailHref(eventId: string): string {
  return `./event-detail.html?event_id=${encodeURIComponent(eventId)}`;
}

export function projectEventTableRows(events: DashboardEventListItem[]): EventTableRowView[] {
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

export function deriveEventsScreenState(
  phase: "loading" | "ready" | "error",
  rowCount: number,
): EventsScreenState {
  if (phase === "loading") {
    return { kind: "loading", message: "이벤트 목록을 불러오는 중입니다." };
  }
  if (phase === "error") {
    return { kind: "error", message: "이벤트 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요." };
  }
  if (rowCount === 0) {
    return { kind: "empty", message: "표시할 이벤트가 없습니다." };
  }
  return { kind: "ready", message: "" };
}

export function safeEventsErrorMessage(status: number): string {
  if (status === 401) return "대시보드 로그인이 필요합니다.";
  if (status === 403) return "대시보드 접근 권한을 확인할 수 없습니다.";
  if (status === 0) return "대시보드 API에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
  return "이벤트 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
}
