import "./styles/main.css";

type EventAction = "Allowed" | "Warned" | "Masked" | "Blocked";
type RouteId = "overview" | "events" | "users" | "filters" | "status";
type RiskLevel = "Low" | "Medium" | "High" | "Critical";

type OverviewStat = {
  label: string;
  value: number;
  tone?: "danger" | "safe" | "warning" | "users";
  description: string;
};

type UserSummary = {
  name: string;
  department: string;
  eventCount: number;
  topSignal: string;
  lastEventAt: string;
};

type EventRecord = {
  id: string;
  occurredAt: string;
  user: string;
  department: string;
  service: string;
  platform: string;
  action: EventAction;
  riskLevel: RiskLevel;
  riskScore: number;
  detectionSummary: string;
  detectionLabels: string[];
  promptHashPrefix: string;
};

const routes: Array<{ id: RouteId; label: string }> = [
  { id: "events", label: "Events" },
  { id: "users", label: "Users" },
  { id: "filters", label: "Filters" },
  { id: "status", label: "Status" }
];

const overviewStats: OverviewStat[] = [
  { label: "Total Events", value: 128, description: "Analyzed AI requests for the selected period" },
  { label: "Blocked", value: 12, tone: "danger", description: "Requests stopped before leaving the workflow" },
  { label: "Masked", value: 38, tone: "safe", description: "Sensitive values replaced before send" },
  { label: "Warned", value: 17, tone: "warning", description: "Requests held for user confirmation" },
  { label: "Active Users", value: 24, tone: "users", description: "Users active in the selected period" }
];

const actionTotals: Record<EventAction, number> = {
  Allowed: 61,
  Blocked: 12,
  Masked: 38,
  Warned: 17
};

const userSummaries: UserSummary[] = [
  { name: "admin", department: "Security", eventCount: 32, topSignal: "Secret", lastEventAt: "2026-05-26" },
  { name: "user01", department: "Sales", eventCount: 28, topSignal: "Contract", lastEventAt: "2026-05-26" },
  { name: "user02", department: "Ops", eventCount: 21, topSignal: "PII", lastEventAt: "2026-05-25" },
  { name: "user03", department: "Planning", eventCount: 18, topSignal: "Strategy", lastEventAt: "2026-05-25" },
  { name: "guest", department: "Support", eventCount: 9, topSignal: "Email", lastEventAt: "2026-05-24" }
];

const periodTotals = [
  { date: "05-20", total: 14 },
  { date: "05-21", total: 18 },
  { date: "05-22", total: 20 },
  { date: "05-23", total: 16 },
  { date: "05-24", total: 24 },
  { date: "05-25", total: 17 },
  { date: "05-26", total: 19 }
];

const events: EventRecord[] = [
  {
    id: "evt_1007",
    occurredAt: "2026-05-26 16:42",
    user: "admin",
    department: "Security",
    service: "ChatGPT",
    platform: "Web",
    action: "Blocked",
    riskLevel: "Critical",
    riskScore: 96,
    detectionSummary: "Secret and policy match",
    detectionLabels: ["Secret", "Internal policy"],
    promptHashPrefix: "hmac_8f41c2"
  },
  {
    id: "evt_1006",
    occurredAt: "2026-05-26 14:18",
    user: "user01",
    department: "Sales",
    service: "Claude",
    platform: "Web",
    action: "Masked",
    riskLevel: "High",
    riskScore: 82,
    detectionSummary: "Contract metadata match",
    detectionLabels: ["Contract", "Client term"],
    promptHashPrefix: "hmac_6ca914"
  },
  {
    id: "evt_1005",
    occurredAt: "2026-05-25 11:03",
    user: "user02",
    department: "Ops",
    service: "ChatGPT",
    platform: "Web",
    action: "Warned",
    riskLevel: "Medium",
    riskScore: 61,
    detectionSummary: "Personal data category match",
    detectionLabels: ["Personal data"],
    promptHashPrefix: "hmac_3b91a0"
  },
  {
    id: "evt_1004",
    occurredAt: "2026-05-25 09:36",
    user: "user01",
    department: "Sales",
    service: "ChatGPT",
    platform: "Web",
    action: "Allowed",
    riskLevel: "Low",
    riskScore: 12,
    detectionSummary: "No policy match",
    detectionLabels: ["None"],
    promptHashPrefix: "hmac_1ab73e"
  }
];

const routePlaceholders: Record<Exclude<RouteId, "overview">, string> = {
  events: "Event list and safe metadata filters will connect here.",
  users: "ADMIN-managed user list and role/status controls will connect here.",
  filters: "Unified Filter Rule Management will connect here.",
  status: "Server health and dependency metadata will connect here."
};

const app = document.querySelector<HTMLDivElement>("#app");

if (!app) {
  throw new Error("Dashboard root element is missing.");
}

const appRoot = app;

function appendText(parent: HTMLElement, tagName: keyof HTMLElementTagNameMap, text: string): HTMLElement {
  const element = document.createElement(tagName);
  element.textContent = text;
  parent.append(element);
  return element;
}

function currentRoute(): RouteId {
  const hash = window.location.hash.replace("#", "");
  return routes.some((route) => route.id === hash) ? (hash as RouteId) : "overview";
}

function renderShell(): { nav: HTMLElement; content: HTMLElement; logoutMessage: HTMLElement } {
  const fragment = document.createDocumentFragment();

  const header = document.createElement("header");
  header.className = "admin-header";

  const headerCopy = document.createElement("div");
  appendText(headerCopy, "p", "OASecure Admin Dashboard").className = "eyebrow";
  appendText(headerCopy, "h1", "관리자 대시보드");
  appendText(headerCopy, "p", "조직의 AI 사용 위험 현황을 안전한 메타데이터로 확인합니다.").className = "header-desc";

  const actions = document.createElement("nav");
  actions.className = "header-actions";
  actions.setAttribute("aria-label", "Dashboard sections");
  const nav = document.createElement("div");
  nav.className = "nav-links";
  actions.append(nav);

  const logoutWrap = document.createElement("div");
  logoutWrap.className = "logout-wrap";
  const logoutButton = appendText(logoutWrap, "button", "로그아웃") as HTMLButtonElement;
  logoutButton.type = "button";
  logoutButton.className = "logout-button";
  const logoutMessage = appendText(logoutWrap, "span", "");
  logoutMessage.className = "session-message";
  logoutButton.addEventListener("click", () => {
    logoutMessage.textContent = "Dashboard session API 연결 후 로그아웃 요청이 실행됩니다.";
  });
  actions.append(logoutWrap);

  header.append(headerCopy, actions);

  const content = document.createElement("main");
  content.className = "dashboard";

  fragment.append(header, content);
  appRoot.replaceChildren(fragment);

  return { nav, content, logoutMessage };
}

function renderNavigation(nav: HTMLElement, activeRoute: RouteId): void {
  nav.replaceChildren();

  const overview = document.createElement("a");
  overview.href = "#overview";
  overview.className = "nav-button";
  overview.textContent = "Overview";
  if (activeRoute === "overview") {
    overview.setAttribute("aria-current", "page");
  }
  nav.append(overview);

  for (const route of routes) {
    const link = document.createElement("a");
    link.href = `#${route.id}`;
    link.className = "nav-button";
    link.textContent = route.label;

    if (route.id === activeRoute) {
      link.setAttribute("aria-current", "page");
    }

    nav.append(link);
  }
}

function renderSectionTitle(title: string, description: string): HTMLElement {
  const wrap = document.createElement("div");
  wrap.className = "section-title-wrap";
  const text = document.createElement("div");
  appendText(text, "h2", title);
  appendText(text, "p", description);
  wrap.append(text);
  return wrap;
}

function renderOverviewCard(stat: OverviewStat): HTMLElement {
  const card = document.createElement("article");
  card.className = stat.tone ? `overview-card ${stat.tone}` : "overview-card";
  appendText(card, "span", stat.label).className = "card-label";
  appendText(card, "strong", String(stat.value));
  appendText(card, "p", stat.description);
  return card;
}

function renderActionChart(): HTMLElement {
  const card = document.createElement("article");
  card.className = "chart-card";
  const title = document.createElement("div");
  title.className = "chart-title";
  appendText(title, "h3", "이벤트별 통계");
  appendText(title, "p", "Allowed, Blocked, Masked, Warned 비율");

  const chart = document.createElement("div");
  chart.className = "bar-chart";
  const max = Math.max(...Object.values(actionTotals));

  for (const [action, total] of Object.entries(actionTotals) as Array<[EventAction, number]>) {
    const row = document.createElement("div");
    row.className = "bar-row";
    appendText(row, "span", action);
    const track = document.createElement("div");
    track.className = "bar-track";
    const fill = document.createElement("i");
    fill.className = `bar-fill ${action.toLowerCase()}`;
    fill.style.width = `${Math.max(8, Math.round((total / max) * 100))}%`;
    track.append(fill);
    appendText(row, "strong", String(total));
    row.insertBefore(track, row.lastChild);
    chart.append(row);
  }

  card.append(title, chart);
  return card;
}

function renderUserChart(): HTMLElement {
  const card = document.createElement("article");
  card.className = "chart-card";
  const title = document.createElement("div");
  title.className = "chart-title";
  appendText(title, "h3", "사용자별 통계");
  appendText(title, "p", "사용자별 AI 요청 및 감지 이벤트");

  const list = document.createElement("ol");
  list.className = "donut-list";
  userSummaries.forEach((user, index) => {
    const item = document.createElement("li");
    item.style.setProperty("--slice-color", ["#2f80ed", "#56ccf2", "#27ae60", "#f2994a", "#9b51e0"][index]);
    appendText(item, "span", user.name);
    appendText(item, "strong", String(user.eventCount));
    list.append(item);
  });

  card.append(title, list);
  return card;
}

function renderPeriodChart(): HTMLElement {
  const card = document.createElement("article");
  card.className = "chart-card wide";
  const title = document.createElement("div");
  title.className = "chart-title";
  appendText(title, "h3", "기간별 통계");
  appendText(title, "p", "최근 7일간 AI 사용 위험 이벤트 추이");

  const chart = document.createElement("div");
  chart.className = "period-chart";
  const max = Math.max(...periodTotals.map((item) => item.total));

  for (const item of periodTotals) {
    const column = document.createElement("div");
    column.className = "period-column";
    const bar = document.createElement("i");
    bar.style.height = `${Math.max(18, Math.round((item.total / max) * 100))}%`;
    appendText(column, "strong", String(item.total));
    column.append(bar);
    appendText(column, "span", item.date);
    chart.append(column);
  }

  card.append(title, chart);
  return card;
}

function renderUserRow(user: UserSummary): HTMLTableRowElement {
  const row = document.createElement("tr");
  appendText(row, "td", user.name);
  appendText(row, "td", user.department);
  appendText(row, "td", user.topSignal);
  appendText(row, "td", String(user.eventCount));
  appendText(row, "td", user.lastEventAt);
  return row;
}

function uniqueValues<T extends keyof EventRecord>(key: T): Array<EventRecord[T]> {
  return [...new Set(events.map((event) => event[key]))];
}

function option(value: string, label = value): HTMLOptionElement {
  const element = document.createElement("option");
  element.value = value;
  element.textContent = label;
  return element;
}

function renderBadge(text: string, className: string): HTMLElement {
  const badge = document.createElement("span");
  badge.className = className;
  badge.textContent = text;
  return badge;
}

function eventMatches(event: EventRecord, action: string, risk: string, service: string): boolean {
  return (!action || event.action === action) && (!risk || event.riskLevel === risk) && (!service || event.service === service);
}

function renderEventDetail(panel: HTMLElement, event: EventRecord): void {
  panel.replaceChildren();
  appendText(panel, "h2", "Event Detail");

  const meta = document.createElement("dl");
  meta.className = "detail-list";

  const fields: Array<[string, string]> = [
    ["Event ID", event.id],
    ["Time", event.occurredAt],
    ["User", `${event.user} / ${event.department}`],
    ["Service", `${event.service} on ${event.platform}`],
    ["Action", event.action],
    ["Risk", `${event.riskLevel} (${event.riskScore})`],
    ["Detection summary", event.detectionSummary],
    ["Prompt hash prefix", event.promptHashPrefix]
  ];

  for (const [label, value] of fields) {
    appendText(meta, "dt", label);
    appendText(meta, "dd", value);
  }

  const labels = document.createElement("div");
  labels.className = "tag-row";
  for (const label of event.detectionLabels) {
    labels.append(renderBadge(label, "tag"));
  }

  panel.append(meta, labels);
}

function renderEventRow(event: EventRecord, onSelect: (event: EventRecord) => void): HTMLTableRowElement {
  const row = document.createElement("tr");
  row.tabIndex = 0;
  row.setAttribute("role", "button");
  row.setAttribute("aria-label", `Open event ${event.id}`);

  appendText(row, "td", event.occurredAt);
  appendText(row, "td", event.user);
  appendText(row, "td", event.service);
  const actionCell = document.createElement("td");
  actionCell.append(renderBadge(event.action, `badge badge--${event.action.toLowerCase()}`));
  row.append(actionCell);
  appendText(row, "td", event.riskLevel);
  appendText(row, "td", String(event.riskScore));

  row.addEventListener("click", () => onSelect(event));
  row.addEventListener("keydown", (keyboardEvent) => {
    if (keyboardEvent.key === "Enter" || keyboardEvent.key === " ") {
      keyboardEvent.preventDefault();
      onSelect(event);
    }
  });

  return row;
}

function renderEvents(content: HTMLElement): void {
  const layout = document.createElement("section");
  layout.className = "events-layout";

  const listPanel = document.createElement("section");
  listPanel.className = "panel";
  const header = document.createElement("div");
  header.className = "panel-header";
  appendText(header, "h2", "Risk Events");
  appendText(header, "p", "Metadata-only event review").className = "muted";

  const filters = document.createElement("form");
  filters.className = "filter-bar";
  filters.setAttribute("aria-label", "Event metadata filters");

  const actionSelect = document.createElement("select");
  actionSelect.append(option("", "All actions"));
  for (const action of uniqueValues("action")) {
    actionSelect.append(option(action));
  }

  const riskSelect = document.createElement("select");
  riskSelect.append(option("", "All risk levels"));
  for (const level of uniqueValues("riskLevel")) {
    riskSelect.append(option(level));
  }

  const serviceSelect = document.createElement("select");
  serviceSelect.append(option("", "All services"));
  for (const service of uniqueValues("service")) {
    serviceSelect.append(option(service));
  }

  filters.append(actionSelect, riskSelect, serviceSelect);

  const tableWrap = document.createElement("div");
  tableWrap.className = "table-wrap";
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const heading of ["Time", "User", "Service", "Action", "Risk", "Score"]) {
    appendText(headRow, "th", heading);
  }
  thead.append(headRow);
  const tbody = document.createElement("tbody");
  table.append(thead, tbody);
  tableWrap.append(table);

  const emptyState = document.createElement("p");
  emptyState.className = "empty-message";
  emptyState.textContent = "No events match the selected metadata filters.";

  const detailPanel = document.createElement("aside");
  detailPanel.className = "panel detail-panel";

  function refresh(): void {
    const visibleEvents = events.filter((event) => eventMatches(event, actionSelect.value, riskSelect.value, serviceSelect.value));
    tbody.replaceChildren(...visibleEvents.map((event) => renderEventRow(event, renderEventDetail.bind(null, detailPanel))));
    emptyState.hidden = visibleEvents.length > 0;

    if (visibleEvents.length > 0) {
      renderEventDetail(detailPanel, visibleEvents[0]);
      return;
    }

    detailPanel.replaceChildren();
    appendText(detailPanel, "h2", "Event Detail");
    appendText(detailPanel, "p", "Select a different metadata filter to review an event.").className = "muted";
  }

  filters.addEventListener("change", refresh);
  listPanel.append(header, filters, tableWrap, emptyState);
  layout.append(listPanel, detailPanel);
  content.replaceChildren(layout);
  refresh();
}

function renderUserTable(): HTMLElement {
  const section = document.createElement("section");
  section.className = "table-section";
  section.append(renderSectionTitle("User Event Summary", "사용자별 주요 감지 유형과 최근 활동"));

  const card = document.createElement("article");
  card.className = "table-card";
  const table = document.createElement("table");
  table.className = "data-table";
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const heading of ["User", "Department", "Top signal", "Events", "Last event"]) {
    appendText(headRow, "th", heading);
  }
  thead.append(headRow);

  const tbody = document.createElement("tbody");
  tbody.append(...userSummaries.map(renderUserRow));
  table.append(thead, tbody);
  card.append(table);
  section.append(card);
  return section;
}

function renderOverview(content: HTMLElement): void {
  const overview = document.createElement("section");
  overview.className = "overview-section";
  overview.append(renderSectionTitle("Overview", "오늘 우리 조직의 AI 사용 위험 현황"));
  const overviewGrid = document.createElement("div");
  overviewGrid.className = "overview-grid";
  overviewGrid.append(...overviewStats.map(renderOverviewCard));
  overview.append(overviewGrid);

  const charts = document.createElement("section");
  charts.className = "chart-section";
  charts.append(renderSectionTitle("Statistics", "이벤트별, 사용자별, 기간별 통계를 확인합니다."));
  const chartGrid = document.createElement("div");
  chartGrid.className = "chart-grid";
  chartGrid.append(renderActionChart(), renderUserChart(), renderPeriodChart());
  charts.append(chartGrid);

  content.replaceChildren(overview, charts, renderUserTable());
}

function renderPlaceholder(content: HTMLElement, route: Exclude<RouteId, "overview">): void {
  const section = document.createElement("section");
  section.className = "table-section";
  section.append(renderSectionTitle(routes.find((item) => item.id === route)?.label ?? "Dashboard", routePlaceholders[route]));

  const card = document.createElement("article");
  card.className = "table-card empty-state";
  appendText(card, "h3", "준비 중");
  appendText(card, "p", "v0.10 API와 세션 계약에 맞춰 다음 PR에서 연결합니다.").className = "muted";
  section.append(card);
  content.replaceChildren(section);
}

const shell = renderShell();

function render(): void {
  const route = currentRoute();
  renderNavigation(shell.nav, route);
  shell.logoutMessage.textContent = "";

  if (route === "overview") {
    renderOverview(shell.content);
    return;
  }

  if (route === "events") {
    renderEvents(shell.content);
    return;
  }

  renderPlaceholder(shell.content, route);
}

window.addEventListener("hashchange", render);
render();
