import "./styles/main.css";

type RouteId = "login" | "admin" | "events" | "users" | "filters" | "status" | "event-detail";
type EventAction = "Block" | "Mask" | "Warn";
type RiskClass = "critical" | "high" | "medium";
type RuleSource = "built_in" | "custom";
type RuleKind = "detector" | "keyword" | "regex" | "context_rule";
type RuleSeverity = "low" | "medium" | "high" | "critical";
type RuleAction = "Allow" | "Warn" | "Mask" | "Block";
type DependencyTone = "healthy" | "degraded" | "unhealthy" | "disabled" | "unknown";

type DependencyStatus = {
  name?: string;
  status?: string;
  required?: boolean;
  code?: string;
  message?: string;
};

type ServerStatus = {
  status?: string;
  service?: string;
  version?: string;
  checked_at?: string;
  api?: DependencyStatus;
  postgres?: DependencyStatus;
  migrations?: DependencyStatus;
  redis?: DependencyStatus;
};

type OverviewStat = {
  label: string;
  value: number;
  tone?: "danger" | "safe" | "warning" | "users";
  description: string;
};

type RiskEvent = {
  eventId: string;
  time: string;
  user: string;
  service: string;
  action: EventAction;
  riskLevel: "Critical" | "High" | "Medium";
  riskClass: RiskClass;
  riskScore: number;
  summary: string;
  detector: string;
  promptHash: string;
  platform: string;
};

type FilterRule = {
  id: string;
  source: RuleSource;
  kind: RuleKind;
  category: string;
  label: string;
  description: string;
  detectorKey?: string;
  keyword?: string;
  pattern?: string;
  placeholder?: string;
  severity: RuleSeverity;
  action: RuleAction;
  enabled: boolean;
  version: number;
  editableFields: string[];
  configJson?: Record<string, unknown> | null;
};

const app = document.querySelector<HTMLDivElement>("#app");

if (!app) {
  throw new Error("Dashboard root element is missing.");
}

const appRoot = app;
let authenticated = false;
let currentFilterPage = 1;
let filterRulesLoadedFromApi = false;
let filterRuleSource: "api" | "fallback" = "fallback";
const filterRowsPerPage = 5;
const apiBaseUrl = (import.meta.env.VITE_PROMPTGUARD_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const dashboardTokenKey = "promptguard_access_token";

// Temporary dashboard preview auth. Replace this mock boundary with API-backed session auth.
const mockDashboardCredentials = {
  username: "admin",
  password: "1234"
};

function isMockDashboardLogin(username: string, password: string): boolean {
  return username === mockDashboardCredentials.username && password === mockDashboardCredentials.password;
}

const overviewStats: OverviewStat[] = [
  { label: "Total Events", value: 128, description: "분석 요청에서 생성된 안전한 메타데이터 이벤트" },
  { label: "Blocked", value: 12, tone: "danger", description: "정책상 즉시 차단된 요청" },
  { label: "Masked", value: 38, tone: "safe", description: "민감정보가 placeholder로 치환된 요청" },
  { label: "Warned", value: 17, tone: "warning", description: "사용자 확인이 필요한 경고 처리" },
  { label: "Active Users", value: 24, tone: "users", description: "기간 내 이벤트가 있는 사용자" }
];

const actionStats: Record<string, number> = {
  Allowed: 61,
  Blocked: 12,
  Masked: 38,
  Warned: 17
};

const userStats: Record<string, number> = {
  ADMIN: 32,
  user01: 28,
  user02: 21,
  user03: 18,
  guest: 9
};

const periodStats: Record<string, number> = {
  "05-20": 14,
  "05-21": 18,
  "05-22": 20,
  "05-23": 16,
  "05-24": 24,
  "05-25": 17,
  "05-26": 19
};

const events: RiskEvent[] = [
  {
    eventId: "EVT-20260529-003",
    time: "10:32",
    user: "김OO",
    service: "ChatGPT",
    action: "Block",
    riskLevel: "Critical",
    riskClass: "critical",
    riskScore: 94,
    summary: "API key 형태의 secret detector match",
    detector: "secret / api_key",
    promptHash: "ph_9a4c",
    platform: "Web"
  },
  {
    eventId: "EVT-20260529-002",
    time: "10:28",
    user: "박OO",
    service: "ChatGPT",
    action: "Mask",
    riskLevel: "High",
    riskClass: "high",
    riskScore: 72,
    summary: "전화번호 형태의 PII detector match",
    detector: "pii / phone",
    promptHash: "ph_7d2a",
    platform: "Web"
  },
  {
    eventId: "EVT-20260529-001",
    time: "10:15",
    user: "최OO",
    service: "ChatGPT",
    action: "Warn",
    riskLevel: "Medium",
    riskClass: "medium",
    riskScore: 51,
    summary: "계약 관련 business context match",
    detector: "business / contract",
    promptHash: "ph_3f81",
    platform: "Web"
  }
];

let filterRules: FilterRule[] = [
  {
    id: "rule-email",
    source: "built_in",
    kind: "detector",
    category: "PII",
    label: "Email Address",
    description: "이메일 주소 형태의 개인정보를 탐지합니다.",
    detectorKey: "EMAIL",
    placeholder: "EMAIL",
    severity: "medium",
    action: "Mask",
    enabled: true,
    version: 1,
    editableFields: ["enabled", "severity", "action"]
  },
  {
    id: "rule-phone",
    source: "built_in",
    kind: "detector",
    category: "PII",
    label: "Phone Number",
    description: "한국 전화번호 후보를 탐지합니다.",
    detectorKey: "PHONE",
    placeholder: "PHONE",
    severity: "medium",
    action: "Mask",
    enabled: true,
    version: 1,
    editableFields: ["enabled", "severity", "action"]
  },
  {
    id: "rule-rrn",
    source: "built_in",
    kind: "detector",
    category: "PII",
    label: "Resident Registration Number",
    description: "checksum이 유효한 주민등록번호 후보를 탐지합니다.",
    detectorKey: "RRN",
    placeholder: "RRN",
    severity: "high",
    action: "Block",
    enabled: true,
    version: 1,
    editableFields: ["enabled", "severity", "action"]
  },
  {
    id: "rule-card",
    source: "built_in",
    kind: "detector",
    category: "Payment",
    label: "Card Number",
    description: "Luhn 검증을 통과한 카드번호 후보를 탐지합니다.",
    detectorKey: "CARD",
    placeholder: "CARD",
    severity: "high",
    action: "Block",
    enabled: true,
    version: 1,
    editableFields: ["enabled", "severity", "action"]
  },
  {
    id: "rule-project",
    source: "custom",
    kind: "keyword",
    category: "Custom",
    label: "Internal Project Name",
    description: "내부 프로젝트 코드명이 외부 AI에 입력되는지 확인합니다.",
    keyword: "Project Hermes",
    placeholder: "INTERNAL_PROJECT",
    severity: "high",
    action: "Mask",
    enabled: true,
    version: 3,
    editableFields: ["label", "description", "keyword", "placeholder", "severity", "action", "enabled"]
  },
  {
    id: "rule-ticket",
    source: "custom",
    kind: "regex",
    category: "Custom",
    label: "Internal Ticket Number",
    description: "내부 티켓 번호 패턴을 탐지합니다.",
    pattern: "INC-[0-9]{6}",
    placeholder: "INTERNAL_TICKET",
    severity: "medium",
    action: "Warn",
    enabled: true,
    version: 2,
    editableFields: ["label", "description", "pattern", "placeholder", "severity", "action", "enabled"]
  },
  {
    id: "rule-contract",
    source: "custom",
    kind: "context_rule",
    category: "Business Context",
    label: "Contract Terms",
    description: "계약, NDA, 할인율, 위약금 등 업무 문맥을 함께 탐지합니다.",
    placeholder: "BUSINESS_CONTEXT",
    severity: "high",
    action: "Warn",
    enabled: true,
    version: 4,
    editableFields: ["label", "description", "config_json", "severity", "action", "enabled"]
  }
];

function appendText(parent: HTMLElement, tagName: keyof HTMLElementTagNameMap, text: string): HTMLElement {
  const element = document.createElement(tagName);
  element.textContent = text;
  parent.append(element);
  return element;
}

function createLink(text: string, hash: string, className: string): HTMLAnchorElement {
  const link = document.createElement("a");
  link.href = hash;
  link.className = className;
  link.textContent = text;
  return link;
}

function navigate(hash: string): void {
  window.location.hash = hash;
}

function normalizeStatus(status?: string): DependencyTone {
  if (status === "healthy" || status === "ok") return "healthy";
  if (status === "degraded") return "degraded";
  if (status === "unhealthy" || status === "error") return "unhealthy";
  if (status === "disabled") return "disabled";
  return "unknown";
}

function statusLabel(status?: string): string {
  const normalized = normalizeStatus(status);
  if (normalized === "healthy") return "Healthy";
  if (normalized === "degraded") return "Degraded";
  if (normalized === "unhealthy") return "Unhealthy";
  if (normalized === "disabled") return "Disabled";
  return "Unknown";
}

function formatCheckedAt(value?: string): string {
  if (!value) return "Not checked";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not checked";
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

function fallbackServerStatus(): ServerStatus {
  return {
    status: "unknown",
    service: "promptguard-api",
    version: "unknown",
    checked_at: new Date().toISOString(),
    api: {
      name: "api",
      status: "unknown",
      required: true,
      message: "Status API is not connected in this dashboard session."
    },
    postgres: {
      name: "postgres",
      status: "unknown",
      required: true,
      message: "PostgreSQL status is unavailable until an API token is connected."
    },
    migrations: {
      name: "migrations",
      status: "unknown",
      required: true,
      message: "Migration readiness is unavailable until an API token is connected."
    },
    redis: {
      name: "redis",
      status: "unknown",
      required: false,
      message: "Redis is optional and was not checked from the fallback view."
    }
  };
}

async function fetchServerStatus(): Promise<{ payload: ServerStatus; source: "api" | "fallback" }> {
  const token = window.localStorage.getItem(dashboardTokenKey);

  if (!token) {
    return { payload: fallbackServerStatus(), source: "fallback" };
  }

  try {
    const response = await fetch(`${apiBaseUrl}/status/server`, {
      headers: {
        Authorization: `Bearer ${token}`
      }
    });
    const payload = (await response.json()) as ServerStatus;
    if (!payload.status && !payload.postgres && !payload.migrations) {
      return { payload: fallbackServerStatus(), source: "fallback" };
    }
    return { payload, source: "api" };
  } catch {
    return { payload: fallbackServerStatus(), source: "fallback" };
  }
}

function toTitleAction(action: string): RuleAction {
  if (action === "ALLOW" || action === "Allow") return "Allow";
  if (action === "WARN" || action === "Warn") return "Warn";
  if (action === "BLOCK" || action === "Block") return "Block";
  return "Mask";
}

function editableFieldNames(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string");
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .filter(([, enabled]) => Boolean(enabled))
      .map(([field]) => field);
  }
  return [];
}

async function fetchFilterRules(): Promise<{ source: "api" | "fallback"; rules: FilterRule[] }> {
  const token = window.localStorage.getItem(dashboardTokenKey);
  if (!token) {
    return { source: "fallback", rules: filterRules };
  }

  try {
    const response = await fetch(`${apiBaseUrl}/filters`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!response.ok) {
      return { source: "fallback", rules: filterRules };
    }
    const payload = (await response.json()) as Array<Record<string, unknown>>;
    return {
      source: "api",
      rules: payload.map((rule) => ({
        id: String(rule.id),
        source: rule.source === "custom" ? "custom" : "built_in",
        kind: String(rule.kind) as RuleKind,
        category: String(rule.category ?? ""),
        label: String(rule.label ?? ""),
        description: String(rule.description ?? ""),
        detectorKey: typeof rule.detector_key === "string" ? rule.detector_key : undefined,
        keyword: typeof rule.keyword === "string" ? rule.keyword : undefined,
        pattern: typeof rule.pattern === "string" ? rule.pattern : undefined,
        placeholder: typeof rule.placeholder === "string" ? rule.placeholder : undefined,
        severity: String(rule.severity ?? "medium") as RuleSeverity,
        action: toTitleAction(String(rule.action ?? "MASK")),
        enabled: Boolean(rule.enabled),
        version: Number(rule.version ?? 1),
        editableFields: editableFieldNames(rule.editable_fields),
        configJson: (rule.config_json as Record<string, unknown> | null | undefined) ?? null
      }))
    };
  } catch {
    return { source: "fallback", rules: filterRules };
  }
}

async function postFilterDryRun(sampleText: string): Promise<Record<string, unknown> | null> {
  const token = window.localStorage.getItem(dashboardTokenKey);
  if (!token) return null;
  try {
    const response = await fetch(`${apiBaseUrl}/filters/dry-run`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ sample_text: sampleText })
    });
    if (!response.ok) return null;
    return (await response.json()) as Record<string, unknown>;
  } catch {
    return null;
  }
}

async function patchFilterEnabled(rule: FilterRule, enabled: boolean): Promise<boolean> {
  const token = window.localStorage.getItem(dashboardTokenKey);
  if (!token) return false;
  try {
    const response = await fetch(`${apiBaseUrl}/filters/${rule.id}/${enabled ? "enable" : "disable"}`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${token}` }
    });
    return response.ok;
  } catch {
    return false;
  }
}

function toApiAction(action: string): string {
  if (action === "Allow") return "ALLOW";
  if (action === "Warn") return "WARN";
  if (action === "Block") return "BLOCK";
  return "MASK";
}

function parseKeywordGroups(value: string): Record<string, string[]> {
  const groups: Record<string, string[]> = {};
  for (const part of value.split("|")) {
    const [name, terms] = part.split(":");
    if (!name || !terms) continue;
    groups[name.trim()] = terms.split(",").map((term) => term.trim()).filter(Boolean);
  }
  return groups;
}

async function createFilterRule(form: HTMLFormElement): Promise<boolean> {
  const token = window.localStorage.getItem(dashboardTokenKey);
  if (!token) return false;
  const data = new FormData(form);
  const kind = String(data.get("kind") ?? "keyword");
  const payload: Record<string, unknown> = {
    kind,
    category: String(data.get("category") ?? "Custom"),
    label: String(data.get("label") ?? "Custom Rule"),
    description: String(data.get("description") ?? ""),
    keyword: String(data.get("keyword") ?? "") || undefined,
    pattern: String(data.get("pattern") ?? "") || undefined,
    placeholder: String(data.get("placeholder") ?? "") || undefined,
    severity: String(data.get("severity") ?? "medium"),
    action: toApiAction(String(data.get("action") ?? "Mask")),
    enabled: data.get("enabled") === "enabled"
  };
  if (kind === "context_rule") {
    payload.config_json = {
      keyword_groups: parseKeywordGroups(String(data.get("keyword_groups") ?? "")),
      min_condition_count: Number(data.get("min_condition_count") ?? 1),
      sensitivity: String(data.get("sensitivity") ?? "medium")
    };
  }
  try {
    const response = await fetch(`${apiBaseUrl}/filters`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });
    return response.ok;
  } catch {
    return false;
  }
}

function routeFromHash(): RouteId {
  const hash = window.location.hash.replace("#", "");

  if (hash.startsWith("events/detail/")) {
    return "event-detail";
  }

  if (hash === "admin" || hash === "events" || hash === "users" || hash === "filters" || hash === "status") {
    return hash;
  }

  return authenticated ? "admin" : "login";
}

function renderHeader(eyebrow: string, title: string, description: string, links: HTMLElement[]): HTMLElement {
  const header = document.createElement("header");
  header.className = "admin-header";

  const copy = document.createElement("div");
  appendText(copy, "p", eyebrow).className = "eyebrow";
  appendText(copy, "h1", title);
  appendText(copy, "p", description).className = "header-desc";

  const nav = document.createElement("nav");
  nav.className = "header-actions";
  nav.append(...links);

  header.append(copy, nav);
  return header;
}

function commonNav(active: RouteId): HTMLElement[] {
  const links = [
    createLink("대시보드", "#admin", "nav-button"),
    createLink("이벤트", "#events", "nav-button"),
    createLink("사용자", "#users", "nav-button"),
    createLink("필터 규칙", "#filters", "nav-button"),
    createLink("Status", "#status", "nav-button"),
    createLink("로그아웃", "#login", "logout-button")
  ];

  for (const link of links) {
    if (link.hash === `#${active}`) {
      link.classList.add("active");
    }
  }

  return links;
}

function renderBadge(text: string, className: string): HTMLElement {
  const badge = document.createElement("span");
  badge.className = className;
  badge.textContent = text;
  return badge;
}

function renderLogin(): void {
  const shell = document.createElement("main");
  shell.className = "login-page";

  const card = document.createElement("section");
  card.className = "login-card";
  appendText(card, "p", "OASecure").className = "eyebrow";
  appendText(card, "h1", "로그인").className = "login-title";

  const form = document.createElement("form");
  form.className = "login-form";

  const idLabel = appendText(form, "label", "아이디");
  const idInput = document.createElement("input");
  idInput.name = "username";
  idInput.type = "text";
  idInput.autocomplete = "username";
  idLabel.append(idInput);

  const passwordLabel = appendText(form, "label", "비밀번호");
  const passwordInput = document.createElement("input");
  passwordInput.name = "password";
  passwordInput.type = "password";
  passwordInput.autocomplete = "current-password";
  passwordLabel.append(passwordInput);

  const message = appendText(form, "p", "");
  message.className = "login-message";

  const button = appendText(form, "button", "로그인") as HTMLButtonElement;
  button.type = "submit";
  button.className = "login-button";

  form.addEventListener("submit", (event) => {
    event.preventDefault();

    if (isMockDashboardLogin(idInput.value, passwordInput.value)) {
      authenticated = true;
      navigate("admin");
      render();
      return;
    }

    message.textContent = "아이디 또는 비밀번호가 올바르지 않습니다.";
  });

  card.append(form);
  shell.append(card);
  appRoot.replaceChildren(shell);
}

function renderOverviewCard(stat: OverviewStat, href?: string): HTMLElement {
  const card = href ? document.createElement("a") : document.createElement("article");
  card.className = stat.tone ? `overview-card ${stat.tone}` : "overview-card";
  if (href) {
    (card as HTMLAnchorElement).href = href;
    card.classList.add("event-link-card");
  }
  appendText(card, "span", stat.label).className = "card-label";
  appendText(card, "strong", String(stat.value));
  appendText(card, "p", stat.description);
  return card;
}

function renderSectionTitle(title: string, description: string): HTMLElement {
  const wrap = document.createElement("div");
  wrap.className = "section-title-wrap";
  const copy = document.createElement("div");
  appendText(copy, "h2", title);
  appendText(copy, "p", description);
  wrap.append(copy);
  return wrap;
}

function renderBarChart(): HTMLElement {
  const chart = document.createElement("div");
  chart.className = "chart-box bar-chart";
  const max = Math.max(...Object.values(actionStats));

  for (const [label, value] of Object.entries(actionStats)) {
    const row = document.createElement("div");
    row.className = "bar-row";
    appendText(row, "span", label);
    const track = document.createElement("div");
    track.className = "bar-track";
    const fill = document.createElement("i");
    fill.className = `bar-fill ${label.toLowerCase()}`;
    fill.style.width = `${Math.max(8, Math.round((value / max) * 100))}%`;
    track.append(fill);
    row.append(track);
    appendText(row, "strong", String(value));
    chart.append(row);
  }

  return chart;
}

function renderUserChart(): HTMLElement {
  const list = document.createElement("ol");
  list.className = "chart-box donut-list";
  const colors = ["#2f80ed", "#56ccf2", "#27ae60", "#f2994a", "#9b51e0"];
  Object.entries(userStats).forEach(([label, value], index) => {
    const item = document.createElement("li");
    item.style.setProperty("--slice-color", colors[index]);
    appendText(item, "span", label);
    appendText(item, "strong", String(value));
    list.append(item);
  });
  return list;
}

function renderPeriodChart(): HTMLElement {
  const chart = document.createElement("div");
  chart.className = "chart-box wide-chart period-chart";
  const max = Math.max(...Object.values(periodStats));

  for (const [date, total] of Object.entries(periodStats)) {
    const column = document.createElement("div");
    column.className = "period-column";
    appendText(column, "strong", String(total));
    const bar = document.createElement("i");
    bar.style.height = `${Math.max(18, Math.round((total / max) * 100))}%`;
    column.append(bar);
    appendText(column, "span", date);
    chart.append(column);
  }

  return chart;
}

function renderDashboard(): void {
  const fragment = document.createDocumentFragment();
  fragment.append(renderHeader("OASecure Admin Dashboard", "관리자 대시보드", "조직의 AI 사용 위험 현황을 원문 없이 확인합니다.", commonNav("admin")));

  const main = document.createElement("main");
  main.className = "dashboard";

  const overview = document.createElement("section");
  overview.className = "overview-section";
  overview.append(renderSectionTitle("Overview", "오늘의 위험 이벤트와 처리 결과 요약"));
  const grid = document.createElement("div");
  grid.className = "overview-grid";
  grid.append(...overviewStats.map((stat) => renderOverviewCard(stat)));
  overview.append(grid);

  const charts = document.createElement("section");
  charts.className = "chart-section";
  charts.append(renderSectionTitle("Statistics", "이벤트, 사용자, 기간별 통계를 빠르게 확인합니다."));
  const chartGrid = document.createElement("div");
  chartGrid.className = "chart-grid";

  const eventCard = document.createElement("article");
  eventCard.className = "chart-card";
  const eventTitle = document.createElement("div");
  eventTitle.className = "chart-title";
  appendText(eventTitle, "h3", "Action 분포");
  appendText(eventTitle, "p", "Allowed, Blocked, Masked, Warned 비율");
  eventCard.append(eventTitle, renderBarChart());

  const userCard = document.createElement("article");
  userCard.className = "chart-card";
  const userTitle = document.createElement("div");
  userTitle.className = "chart-title";
  appendText(userTitle, "h3", "사용자별 이벤트");
  appendText(userTitle, "p", "사용자별 안전한 aggregate count");
  userCard.append(userTitle, renderUserChart());

  const periodCard = document.createElement("article");
  periodCard.className = "chart-card wide";
  const periodTitle = document.createElement("div");
  periodTitle.className = "chart-title";
  appendText(periodTitle, "h3", "기간별 추이");
  appendText(periodTitle, "p", "최근 7일 이벤트 수");
  periodCard.append(periodTitle, renderPeriodChart());

  chartGrid.append(eventCard, userCard, periodCard);
  charts.append(chartGrid);
  main.append(overview, charts);
  fragment.append(main);
  appRoot.replaceChildren(fragment);
}

function renderEventRow(event: RiskEvent): HTMLTableRowElement {
  const row = document.createElement("tr");
  appendText(row, "td", event.time);
  appendText(row, "td", event.user);
  appendText(row, "td", event.service);

  const actionCell = document.createElement("td");
  actionCell.append(renderBadge(event.action, `status-badge result-${event.action.toLowerCase()}ed`));
  row.append(actionCell);

  const riskCell = document.createElement("td");
  riskCell.append(renderBadge(event.riskLevel, `risk-badge risk-${event.riskClass}`));
  row.append(riskCell);
  appendText(row, "td", event.detector.split(" / ")[1] ?? event.detector);
  return row;
}

function renderEvents(): void {
  const fragment = document.createDocumentFragment();
  fragment.append(renderHeader("OASecure Event Monitoring", "이벤트 관리", "탐지된 위험 이벤트를 원문 없이 확인합니다.", commonNav("events")));

  const main = document.createElement("main");
  main.className = "dashboard";

  const overview = document.createElement("section");
  overview.className = "overview-section";
  overview.append(renderSectionTitle("Events Overview", "오늘의 탐지 이벤트 요약"));
  const grid = document.createElement("div");
  grid.className = "overview-grid event-overview-grid";
  grid.append(
    renderOverviewCard({ label: "Total Events", value: events.length, description: "전체 탐지 이벤트" }, "#events/detail/all"),
    renderOverviewCard({ label: "Critical", value: events.filter((event) => event.riskClass === "critical").length, tone: "danger", description: "즉시 차단 대상" }, "#events/detail/critical"),
    renderOverviewCard({ label: "High", value: events.filter((event) => event.riskClass === "high").length, tone: "warning", description: "주의 확인 대상" }, "#events/detail/high"),
    renderOverviewCard({ label: "Medium", value: events.filter((event) => event.riskClass === "medium").length, tone: "safe", description: "모니터링 대상" }, "#events/detail/medium")
  );
  overview.append(grid);

  const tableSection = document.createElement("section");
  tableSection.className = "table-section";
  tableSection.append(renderSectionTitle("Risk Events", "prompt 원문과 탐지 원문값 없이 메타데이터만 표시합니다."));
  const card = document.createElement("div");
  card.className = "table-card";
  const table = document.createElement("table");
  table.className = "data-table";
  const thead = document.createElement("thead");
  const head = document.createElement("tr");
  for (const label of ["시간", "사용자", "서비스", "Action", "위험도", "탐지 유형"]) {
    appendText(head, "th", label);
  }
  thead.append(head);
  const tbody = document.createElement("tbody");
  tbody.append(...events.map(renderEventRow));
  table.append(thead, tbody);
  card.append(table);
  tableSection.append(card);

  main.append(overview, tableSection);
  fragment.append(main);
  appRoot.replaceChildren(fragment);
}

function eventDetailTitle(filter: string): string {
  if (filter === "critical") return "Critical 이벤트 상세";
  if (filter === "high") return "High 이벤트 상세";
  if (filter === "medium") return "Medium 이벤트 상세";
  return "전체 이벤트 상세";
}

function filteredEvents(): RiskEvent[] {
  const filter = window.location.hash.replace("#events/detail/", "");
  if (filter === "critical" || filter === "high" || filter === "medium") {
    return events.filter((event) => event.riskClass === filter);
  }
  return events;
}

function renderBoardRows(items: RiskEvent[]): HTMLTableRowElement[] {
  return items.flatMap((event, index) => {
    const row = document.createElement("tr");
    row.className = "board-row";
    appendText(row, "td", String(index + 1));

    const titleCell = document.createElement("td");
    const button = document.createElement("button");
    button.className = "board-title-button";
    button.type = "button";
    const icon = appendText(button, "span", "+");
    icon.className = "toggle-icon";
    button.append(document.createTextNode(event.summary));
    titleCell.append(button);
    row.append(titleCell);

    appendText(row, "td", event.user);
    const riskCell = document.createElement("td");
    riskCell.append(renderBadge(event.riskLevel, `risk-badge risk-${event.riskClass}`));
    row.append(riskCell);
    appendText(row, "td", event.action);
    appendText(row, "td", event.time);

    const detailRow = document.createElement("tr");
    detailRow.className = "board-detail-row";
    const detailCell = document.createElement("td");
    detailCell.colSpan = 6;
    const detailBox = document.createElement("div");
    detailBox.className = "board-detail-box";
    const fields: Array<[string, string]> = [
      ["이벤트 ID", event.eventId],
      ["시간", event.time],
      ["사용자", event.user],
      ["서비스", event.service],
      ["Action", event.action],
      ["위험 점수", String(event.riskScore)],
      ["위험도", event.riskLevel],
      ["탐지 요약", event.summary],
      ["탐지 항목", event.detector],
      ["프롬프트 해시", event.promptHash],
      ["플랫폼", event.platform]
    ];

    for (const [label, value] of fields) {
      const item = document.createElement("div");
      appendText(item, "span", label);
      appendText(item, "strong", value);
      detailBox.append(item);
    }

    detailCell.append(detailBox);
    detailRow.append(detailCell);

    button.addEventListener("click", () => {
      const isOpen = detailRow.style.display === "table-row";
      detailRow.style.display = isOpen ? "none" : "table-row";
      icon.textContent = isOpen ? "+" : "-";
    });

    return [row, detailRow];
  });
}

function renderEventDetail(): void {
  const filter = window.location.hash.replace("#events/detail/", "");
  const fragment = document.createDocumentFragment();
  fragment.append(renderHeader("OASecure Event Detail", eventDetailTitle(filter), "선택한 위험도에 해당하는 이벤트를 상세 확인합니다.", commonNav("events")));

  const main = document.createElement("main");
  main.className = "dashboard";
  const section = document.createElement("section");
  section.className = "table-section";
  section.append(renderSectionTitle("상세 이벤트", "원문 prompt와 주변 문맥은 표시하지 않습니다."));

  const card = document.createElement("div");
  card.className = "table-card";
  const table = document.createElement("table");
  table.className = "data-table detail-board-table";
  const thead = document.createElement("thead");
  const head = document.createElement("tr");
  for (const label of ["No.", "제목", "사용자", "위험도", "Action", "시간"]) {
    appendText(head, "th", label);
  }
  thead.append(head);
  const tbody = document.createElement("tbody");
  tbody.append(...renderBoardRows(filteredEvents()));
  table.append(thead, tbody);
  card.append(table);
  section.append(card);
  main.append(section);
  fragment.append(main);
  appRoot.replaceChildren(fragment);
}

function renderUsers(): void {
  const fragment = document.createDocumentFragment();
  fragment.append(renderHeader("OASecure User Management", "사용자 관리", "관리자 화면에서 사용자 상태와 권한을 확인합니다.", commonNav("users")));
  const main = document.createElement("main");
  main.className = "dashboard";
  const section = document.createElement("section");
  section.className = "table-section";
  section.append(renderSectionTitle("Users", "목록, 추가, role/status 변경 UI가 들어갈 자리입니다."));
  const card = document.createElement("div");
  card.className = "table-card";
  appendText(card, "p", "사용자 관리 상세 기능은 다음 단계에서 API와 연결합니다. hard delete는 제공하지 않습니다.").className = "notice-text";
  section.append(card);
  main.append(section);
  fragment.append(main);
  appRoot.replaceChildren(fragment);
}

function createField(labelText: string, control: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement): HTMLLabelElement {
  const label = document.createElement("label");
  label.textContent = labelText;
  control.name = labelText.replaceAll(" ", "_");
  label.append(control);
  return label;
}

function createInput(value: string, placeholder = ""): HTMLInputElement {
  const input = document.createElement("input");
  input.value = value;
  input.placeholder = placeholder;
  return input;
}

function createSelect(values: string[], selected: string): HTMLSelectElement {
  const select = document.createElement("select");
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    option.selected = value === selected;
    select.append(option);
  }
  return select;
}

function renderFilterForm(): HTMLElement {
  const card = document.createElement("article");
  card.className = "filter-card";

  const header = document.createElement("div");
  header.className = "filter-card-header";
  const copy = document.createElement("div");
  appendText(copy, "h2", "Filter Rule 설정");
  appendText(copy, "p", "custom keyword, regex, context_rule을 생성하고 built-in detector는 허용 필드만 조정합니다.");
  appendText(header, "span", "Create Mode").className = "filter-pill";
  header.prepend(copy);

  const tabs = document.createElement("div");
  tabs.className = "filter-tabs";
  const kindSelect = createSelect(["context_rule", "keyword", "regex", "detector"], "context_rule");
  for (const [label, kind] of [
    ["Business Context", "context_rule"],
    ["Keyword", "keyword"],
    ["Regex", "regex"],
    ["Detector", "detector"]
  ]) {
    const tab = document.createElement("button");
    tab.type = "button";
    tab.className = kind === "context_rule" ? "filter-tab active" : "filter-tab";
    tab.textContent = label;
    tab.addEventListener("click", () => {
      tabs.querySelectorAll(".filter-tab").forEach((item) => item.classList.remove("active"));
      tab.classList.add("active");
      kindSelect.value = kind;
    });
    tabs.append(tab);
  }

  const form = document.createElement("form");
  form.className = "filter-form";

  const row1 = document.createElement("div");
  row1.className = "form-row";
  row1.append(createField("source", createSelect(["custom", "built_in"], "custom")), createField("kind", kindSelect));

  const row2 = document.createElement("div");
  row2.className = "form-row";
  row2.append(createField("category", createInput("Business Context")), createField("label", createInput("", "예: Contract Terms")));

  const description = createField("description", createInput("", "관리자가 이해할 수 있는 설명"));

  const row3 = document.createElement("div");
  row3.className = "form-row";
  row3.append(createField("keyword", createInput("", "kind=keyword일 때 사용")), createField("pattern", createInput("", "예: INC-[0-9]{6}")));

  const row4 = document.createElement("div");
  row4.className = "form-row";
  row4.append(createField("placeholder", createInput("", "예: INTERNAL_PROJECT")), createField("detector_key", createInput("", "built-in detector read-only")));

  const row5 = document.createElement("div");
  row5.className = "form-row three";
  row5.append(
    createField("severity", createSelect(["low", "medium", "high", "critical"], "high")),
    createField("action", createSelect(["Allow", "Warn", "Mask", "Block"], "Mask")),
    createField("enabled", createSelect(["enabled", "disabled"], "enabled"))
  );

  const contextBox = document.createElement("div");
  contextBox.className = "context-box";
  appendText(contextBox, "h3", "Business Context 설정");
  const keywordGroups = document.createElement("textarea");
  keywordGroups.value = "contract_terms:계약,NDA,위약금,갱신,해지 | money_terms:만원,%,할인,견적";
  contextBox.append(createField("keyword groups", keywordGroups));
  contextBox.append(createField("exclusion keywords", createInput("샘플, 교육용, 공개 문서")));
  const contextRow = document.createElement("div");
  contextRow.className = "form-row three";
  contextRow.append(
    createField("window size", createInput("500")),
    createField("min condition count", createInput("2")),
    createField("sensitivity", createSelect(["low", "medium", "high"], "medium"))
  );
  contextBox.append(contextRow);

  const privacyNotice = document.createElement("p");
  privacyNotice.className = "privacy-note";
  privacyNotice.textContent = "Dry-run sample과 원문 탐지값은 저장하지 않습니다. 화면에는 metadata-only 결과만 표시합니다.";

  const actions = document.createElement("div");
  actions.className = "form-actions";
  const reset = appendText(actions, "button", "초기화") as HTMLButtonElement;
  reset.type = "button";
  reset.className = "nav-button";
  const save = appendText(actions, "button", "규칙 저장") as HTMLButtonElement;
  save.type = "submit";
  save.className = "logout-button";
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const created = await createFilterRule(form);
    if (created) {
      filterRulesLoadedFromApi = false;
      form.reset();
      renderFilters();
    }
  });

  form.append(tabs, row1, row2, description, row3, row4, row5, contextBox, privacyNotice, actions);
  card.append(header, form);
  return card;
}

function renderDryRun(): HTMLElement {
  const card = document.createElement("article");
  card.className = "filter-card dryrun-card";
  appendText(card, "h2", "Dry-run Test");
  appendText(card, "p", "샘플 텍스트는 저장하지 않고 예상 action과 안전한 match metadata만 확인합니다.").className = "filter-subtext";

  const sample = document.createElement("textarea");
  sample.className = "dryrun-textarea";
  sample.value = "계약서에 NDA와 위약금 조건, 15% 할인율이 포함되어 있는지 확인해줘.";
  card.append(createField("sample text", sample));

  const run = appendText(card, "button", "dry-run 실행") as HTMLButtonElement;
  run.type = "button";
  run.className = "logout-button full-button";

  const result = document.createElement("div");
  result.className = "dryrun-result";
  appendText(result, "h3", "dry-run 결과");
  appendText(result, "p", "아직 실행된 dry-run 결과가 없습니다.").className = "empty-state";

  run.addEventListener("click", async () => {
    const text = sample.value;
    const apiResult = await postFilterDryRun(text);
    result.replaceChildren();
    appendText(result, "h3", "dry-run 결과");
    const detections = Array.isArray(apiResult?.detections) ? apiResult.detections : [];
    const rows: Array<[string, string, string?]> = apiResult
      ? [
          ["matched", String(Boolean(apiResult.matched)), Boolean(apiResult.matched) ? "danger-text" : "safe-text"],
          ["expected_action", String(apiResult.expected_action ?? "ALLOW")],
          ["risk_level", String(apiResult.risk_level ?? "low")],
          ["risk_score", String(apiResult.risk_score ?? 0)],
          ["match_count", String(detections.length)],
          ["filter_version", String(apiResult.filter_rule_set_version ?? "unknown")],
          ["sample_persisted", "false", "safe-text"]
        ]
      : [
          ["matched", "unknown", "safe-text"],
          ["expected_action", "API token required"],
          ["risk_level", "unknown"],
          ["match_count", "0"],
          ["sample_persisted", "false", "safe-text"]
        ];
    for (const [label, value, className] of rows) {
      const row = document.createElement("div");
      row.className = "result-row";
      appendText(row, "span", label);
      const strong = appendText(row, "strong", value);
      if (className) strong.className = className;
      result.append(row);
    }
  });

  card.append(result);
  return card;
}

function renderRuleRow(rule: FilterRule): HTMLTableRowElement {
  const row = document.createElement("tr");
  const sourceCell = document.createElement("td");
  sourceCell.append(renderBadge(rule.source, `source-badge ${rule.source}`));
  row.append(sourceCell);
  appendText(row, "td", rule.kind);
  appendText(row, "td", rule.category);

  const labelCell = document.createElement("td");
  appendText(labelCell, "strong", rule.label);
  appendText(labelCell, "small", rule.description);
  appendText(labelCell, "small", `editable: ${rule.editableFields.join(", ") || "none"}`);
  row.append(labelCell);

  const severityCell = document.createElement("td");
  severityCell.append(renderBadge(rule.severity, `severity-badge ${rule.severity}`));
  row.append(severityCell);
  appendText(row, "td", rule.action);
  const statusCell = document.createElement("td");
  statusCell.append(renderBadge(rule.enabled ? "ON" : "OFF", `user-status ${rule.enabled ? "active" : "disabled"}`));
  row.append(statusCell);
  appendText(row, "td", `v${rule.version}`);

  const actions = document.createElement("td");
  const edit = appendText(actions, "button", rule.source === "built_in" ? "허용 필드 수정" : "수정") as HTMLButtonElement;
  edit.type = "button";
  edit.className = "text-action";
  const toggle = appendText(actions, "button", rule.enabled ? "비활성화" : "활성화") as HTMLButtonElement;
  toggle.type = "button";
  toggle.className = "text-action";
  toggle.addEventListener("click", async () => {
    const updated = await patchFilterEnabled(rule, !rule.enabled);
    if (updated) {
      filterRulesLoadedFromApi = false;
      renderFilters();
    }
  });
  row.append(actions);
  return row;
}

function renderRuleTable(): HTMLElement {
  const section = document.createElement("section");
  section.className = "table-section";
  const top = renderSectionTitle("등록된 Filter Rules", "built-in은 삭제하지 않고 editable_fields에 허용된 값만 변경합니다.");
  const pageInfo = appendText(top, "span", "");
  pageInfo.className = "filter-page-info";
  section.append(top);

  const card = document.createElement("div");
  card.className = "table-card";
  const table = document.createElement("table");
  table.className = "data-table filter-table";
  const thead = document.createElement("thead");
  const head = document.createElement("tr");
  for (const label of ["source", "kind", "category", "label", "severity", "action", "status", "version", "관리"]) {
    appendText(head, "th", label);
  }
  thead.append(head);
  const tbody = document.createElement("tbody");
  table.append(thead, tbody);
  card.append(table);

  const pagination = document.createElement("div");
  pagination.className = "pagination";
  const prev = appendText(pagination, "button", "이전") as HTMLButtonElement;
  prev.type = "button";
  prev.className = "page-btn";
  const numbers = document.createElement("div");
  numbers.className = "page-numbers";
  const next = appendText(pagination, "button", "다음") as HTMLButtonElement;
  next.type = "button";
  next.className = "page-btn";
  pagination.append(numbers, next);

  function paint(): void {
    const totalPages = Math.ceil(filterRules.length / filterRowsPerPage);
    const start = (currentFilterPage - 1) * filterRowsPerPage;
    tbody.replaceChildren(...filterRules.slice(start, start + filterRowsPerPage).map(renderRuleRow));
    pageInfo.textContent = `${currentFilterPage} / ${totalPages} 페이지`;
    numbers.replaceChildren();
    for (let page = 1; page <= totalPages; page += 1) {
      const button = appendText(numbers, "button", String(page)) as HTMLButtonElement;
      button.type = "button";
      button.className = page === currentFilterPage ? "page-number active" : "page-number";
      button.addEventListener("click", () => {
        currentFilterPage = page;
        paint();
      });
    }
    prev.disabled = currentFilterPage === 1;
    next.disabled = currentFilterPage === totalPages;
  }

  prev.addEventListener("click", () => {
    if (currentFilterPage > 1) {
      currentFilterPage -= 1;
      paint();
    }
  });
  next.addEventListener("click", () => {
    const totalPages = Math.ceil(filterRules.length / filterRowsPerPage);
    if (currentFilterPage < totalPages) {
      currentFilterPage += 1;
      paint();
    }
  });

  paint();
  section.append(card, pagination);
  return section;
}

function renderFilters(): void {
  currentFilterPage = 1;
  const fragment = document.createDocumentFragment();
  fragment.append(renderHeader("OASecure Admin / Filter Policy", "Filter Rule 관리", "기본 탐지 규칙, 사용자 정의 keyword/regex, Business Context 규칙을 하나의 화면에서 관리합니다.", commonNav("filters")));

  const main = document.createElement("main");
  main.className = "dashboard filter-dashboard";
  const summary = document.createElement("section");
  summary.className = "filter-summary";
  appendText(summary, "strong", "v0.10 통합 Filter Rule 화면");
  appendText(summary, "p", `source/kind/category 목록, built-in 수정 제한, custom keyword/regex/context_rule form, 저장 없는 dry-run panel을 포함합니다. source=${filterRuleSource}`);

  const grid = document.createElement("section");
  grid.className = "filter-grid";
  grid.append(renderFilterForm(), renderDryRun());

  main.append(summary, grid, renderRuleTable());
  fragment.append(main);
  appRoot.replaceChildren(fragment);

  if (!filterRulesLoadedFromApi) {
    void fetchFilterRules().then(({ source, rules }) => {
      if (routeFromHash() !== "filters") return;
      filterRuleSource = source;
      filterRules = rules;
      filterRulesLoadedFromApi = true;
      renderFilters();
    });
  }
}

function renderDependencyCard(label: string, dependency?: DependencyStatus): HTMLElement {
  const card = document.createElement("article");
  card.className = "dependency-card";

  const header = document.createElement("div");
  header.className = "dependency-card-header";
  appendText(header, "strong", label);
  header.append(renderBadge(statusLabel(dependency?.status), `health-badge ${normalizeStatus(dependency?.status)}`));

  const meta = document.createElement("dl");
  meta.className = "dependency-meta";
  appendText(meta, "dt", "Role");
  appendText(meta, "dd", dependency?.required === false ? "Optional" : "Required");
  appendText(meta, "dt", "Message");
  appendText(meta, "dd", dependency?.message ?? "No additional details reported.");

  card.append(header, meta);
  return card;
}

function buildStatusView(payload: ServerStatus, source: "api" | "fallback"): HTMLElement {
  const main = document.createElement("main");
  main.className = "dashboard status-dashboard";

  const summary = document.createElement("section");
  summary.className = "status-summary-card";

  const copy = document.createElement("div");
  appendText(copy, "p", "Server Status").className = "eyebrow";
  appendText(copy, "h2", statusLabel(payload.status));
  appendText(copy, "p", source === "api" ? "Live metadata from the server status endpoint." : "Safe fallback metadata. Connect an API token to read live server status.").className = "status-summary-copy";

  const badgeGroup = document.createElement("div");
  badgeGroup.className = "status-badge-group";
  badgeGroup.append(renderBadge(statusLabel(payload.status), `health-badge ${normalizeStatus(payload.status)}`));
  badgeGroup.append(renderBadge(source === "api" ? "Live API" : "Fallback", `source-badge ${source === "api" ? "built_in" : "custom"}`));

  summary.append(copy, badgeGroup);

  const meta = document.createElement("section");
  meta.className = "status-meta-grid";
  const metaItems = [
    ["Service", payload.service ?? "unknown"],
    ["Version", payload.version ?? "unknown"],
    ["Last Checked", formatCheckedAt(payload.checked_at)]
  ];
  for (const [label, value] of metaItems) {
    const item = document.createElement("article");
    item.className = "status-meta-card";
    appendText(item, "span", label);
    appendText(item, "strong", value);
    meta.append(item);
  }

  const dependencies = document.createElement("section");
  dependencies.className = "dependency-grid";
  dependencies.append(
    renderDependencyCard("API", payload.api ?? { status: payload.status, required: true }),
    renderDependencyCard("PostgreSQL", payload.postgres),
    renderDependencyCard("Migration", payload.migrations),
    renderDependencyCard("Redis", payload.redis ?? { status: "unknown", required: false, message: "Redis status is not exposed by the current dashboard status payload." })
  );

  main.append(summary, meta, dependencies);
  return main;
}

function renderStatus(): void {
  const fragment = document.createDocumentFragment();
  fragment.append(renderHeader("OASecure Admin / Status", "Server Status", "API, PostgreSQL, migration, Redis readiness metadata를 확인합니다.", commonNav("status")));

  const loading = document.createElement("main");
  loading.className = "dashboard status-dashboard";
  const card = document.createElement("section");
  card.className = "status-summary-card";
  appendText(card, "p", "Loading status metadata...");
  loading.append(card);
  fragment.append(loading);
  appRoot.replaceChildren(fragment);

  void fetchServerStatus().then(({ payload, source }) => {
    if (routeFromHash() !== "status") return;
    const next = document.createDocumentFragment();
    next.append(renderHeader("OASecure Admin / Status", "Server Status", "API, PostgreSQL, migration, Redis readiness metadata를 확인합니다.", commonNav("status")));
    next.append(buildStatusView(payload, source));
    appRoot.replaceChildren(next);
  });
}

function render(): void {
  const route = routeFromHash();

  if (window.location.hash === "#login") {
    authenticated = false;
  }

  if (!authenticated && route !== "login") {
    renderLogin();
    return;
  }

  if (route === "login") renderLogin();
  if (route === "admin") renderDashboard();
  if (route === "events") renderEvents();
  if (route === "event-detail") renderEventDetail();
  if (route === "users") renderUsers();
  if (route === "filters") renderFilters();
  if (route === "status") renderStatus();
}

window.addEventListener("hashchange", render);
render();
