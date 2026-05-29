import "./styles/main.css";

type RouteId = "login" | "admin" | "events" | "users" | "event-detail";
type EventAction = "Block" | "Mask" | "Warn";
type RiskClass = "critical" | "high" | "medium";

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

const app = document.querySelector<HTMLDivElement>("#app");

if (!app) {
  throw new Error("Dashboard root element is missing.");
}

const appRoot = app;
let authenticated = false;

const overviewStats: OverviewStat[] = [
  { label: "Total Events", value: 128, description: "분석된 프롬프트/파일 요청 수" },
  { label: "Blocked", value: 12, tone: "danger", description: "위험도가 높아 차단된 건수" },
  { label: "Masked", value: 38, tone: "safe", description: "민감정보가 마스킹된 건수" },
  { label: "Warned", value: 17, tone: "warning", description: "사용자에게 경고 처리된 건수" },
  { label: "Active Users", value: 24, tone: "users", description: "기간 내 사용한 사용자 수" }
];

const actionStats: Record<string, number> = {
  Allowed: 61,
  Blocked: 12,
  Masked: 38,
  Warned: 17
};

const userStats: Record<string, number> = {
  admin: 32,
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
    summary: "API Key 형태의 민감정보 탐지",
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
    summary: "전화번호 형태의 개인정보 탐지",
    detector: "pii / phone",
    promptHash: "ph_7d2a",
    platform: "Web"
  },
  {
    eventId: "EVT-20260529-001",
    time: "10:15",
    user: "이OO",
    service: "ChatGPT",
    action: "Warn",
    riskLevel: "Medium",
    riskClass: "medium",
    riskScore: 51,
    summary: "계약 관련 내부 정보 탐지",
    detector: "business / contract",
    promptHash: "ph_3f81",
    platform: "Web"
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

function routeFromHash(): RouteId {
  const hash = window.location.hash.replace("#", "");

  if (hash.startsWith("events/detail/")) {
    return "event-detail";
  }

  if (hash === "admin" || hash === "events" || hash === "users") {
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

function renderLogin(): void {
  const shell = document.createElement("main");
  shell.className = "login-page";

  const card = document.createElement("section");
  card.className = "login-card";
  appendText(card, "p", "OASecure Admin Dashboard").className = "eyebrow";
  appendText(card, "h1", "관리자 로그인");
  appendText(card, "p", "관리자 계정으로 로그인하면 대시보드와 이벤트 관리 화면을 확인할 수 있습니다.").className = "login-desc";

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

    if (idInput.value === "admin" && passwordInput.value === "1234") {
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
  fragment.append(
    renderHeader("OASecure Admin Dashboard", "관리자 대시보드", "오늘 우리 조직의 AI 사용 위험 현황을 한눈에 확인합니다.", [
      createLink("이벤트 관리", "#events", "nav-button"),
      createLink("사용자 관리", "#users", "nav-button"),
      createLink("로그아웃", "#login", "logout-button")
    ])
  );

  const main = document.createElement("main");
  main.className = "dashboard";

  const overview = document.createElement("section");
  overview.className = "overview-section";
  overview.append(renderSectionTitle("Overview", "오늘 우리 조직의 AI 사용 위험 현황"));
  const grid = document.createElement("div");
  grid.className = "overview-grid";
  grid.append(...overviewStats.map((stat) => renderOverviewCard(stat)));
  overview.append(grid);

  const charts = document.createElement("section");
  charts.className = "chart-section";
  charts.append(renderSectionTitle("Statistics", "이벤트별, 사용자별, 기간별 통계를 차트로 확인합니다."));
  const chartGrid = document.createElement("div");
  chartGrid.className = "chart-grid";

  const eventCard = document.createElement("article");
  eventCard.className = "chart-card";
  const eventTitle = document.createElement("div");
  eventTitle.className = "chart-title";
  appendText(eventTitle, "h3", "이벤트별 통계");
  appendText(eventTitle, "p", "Allowed, Blocked, Masked, Warned 비율");
  eventCard.append(eventTitle, renderBarChart());

  const userCard = document.createElement("article");
  userCard.className = "chart-card";
  const userTitle = document.createElement("div");
  userTitle.className = "chart-title";
  appendText(userTitle, "h3", "사용자별 통계");
  appendText(userTitle, "p", "사용자별 AI 요청/탐지 이벤트 수");
  userCard.append(userTitle, renderUserChart());

  const periodCard = document.createElement("article");
  periodCard.className = "chart-card wide";
  const periodTitle = document.createElement("div");
  periodTitle.className = "chart-title";
  appendText(periodTitle, "h3", "기간별 통계");
  appendText(periodTitle, "p", "최근 7일간 AI 사용 위험 이벤트 추이");
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

function renderBadge(text: string, className: string): HTMLElement {
  const badge = document.createElement("span");
  badge.className = className;
  badge.textContent = text;
  return badge;
}

function renderEvents(): void {
  const fragment = document.createDocumentFragment();
  fragment.append(
    renderHeader("OASecure Event Monitoring", "이벤트 관리", "탐지된 위험 이벤트를 확인하고 상세 정보를 조회합니다.", [
      createLink("대시보드", "#admin", "nav-button"),
      createLink("사용자 관리", "#users", "nav-button"),
      createLink("로그아웃", "#login", "logout-button")
    ])
  );

  const main = document.createElement("main");
  main.className = "dashboard";

  const overview = document.createElement("section");
  overview.className = "overview-section";
  overview.append(renderSectionTitle("Events Overview", "오늘 탐지된 위험 이벤트 현황"));
  const grid = document.createElement("div");
  grid.className = "overview-grid event-overview-grid";
  grid.append(
    renderOverviewCard({ label: "Total Events", value: events.length, description: "전체 탐지 이벤트 수" }, "#events/detail/all"),
    renderOverviewCard({ label: "Critical", value: events.filter((event) => event.riskClass === "critical").length, tone: "danger", description: "즉시 차단이 필요한 이벤트" }, "#events/detail/critical"),
    renderOverviewCard({ label: "High", value: events.filter((event) => event.riskClass === "high").length, tone: "warning", description: "주의 깊게 확인해야 하는 이벤트" }, "#events/detail/high"),
    renderOverviewCard({ label: "Medium", value: events.filter((event) => event.riskClass === "medium").length, tone: "safe", description: "모니터링이 필요한 이벤트" }, "#events/detail/medium")
  );
  overview.append(grid);

  const tableSection = document.createElement("section");
  tableSection.className = "table-section";
  tableSection.append(renderSectionTitle("Risk Events", "원문 프롬프트는 저장하지 않고 탐지 결과만 표시합니다."));
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
  if (filter === "critical") return "Critical 이벤트 상세보기";
  if (filter === "high") return "High 이벤트 상세보기";
  if (filter === "medium") return "Medium 이벤트 상세보기";
  return "전체 이벤트 상세보기";
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
    const icon = appendText(button, "span", "＋");
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
      ["위험도 점수", String(event.riskScore)],
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
      icon.textContent = isOpen ? "＋" : "－";
    });

    return [row, detailRow];
  });
}

function renderEventDetail(): void {
  const filter = window.location.hash.replace("#events/detail/", "");
  const fragment = document.createDocumentFragment();
  fragment.append(
    renderHeader("OASecure Event Detail", eventDetailTitle(filter), "선택한 위험도에 해당하는 이벤트 제목을 클릭하면 상세 내용을 확인할 수 있습니다.", [
      createLink("이벤트 목록", "#events", "nav-button"),
      createLink("대시보드", "#admin", "nav-button"),
      createLink("로그아웃", "#login", "logout-button")
    ])
  );

  const main = document.createElement("main");
  main.className = "dashboard";
  const section = document.createElement("section");
  section.className = "table-section";
  section.append(renderSectionTitle("상세 이벤트 게시판", "원문 프롬프트는 저장하지 않고 탐지 결과만 표시합니다."));

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
  fragment.append(
    renderHeader("OASecure User Management", "사용자 관리", "관리자 화면에서 사용자 상태와 권한을 확인합니다.", [
      createLink("대시보드", "#admin", "nav-button"),
      createLink("이벤트 관리", "#events", "nav-button"),
      createLink("로그아웃", "#login", "logout-button")
    ])
  );
  const main = document.createElement("main");
  main.className = "dashboard";
  const section = document.createElement("section");
  section.className = "table-section";
  section.append(renderSectionTitle("Users", "사용자별 이벤트 수와 상태를 확인합니다."));
  const card = document.createElement("div");
  card.className = "table-card";
  appendText(card, "p", "사용자 관리 상세 기능은 다음 단계에서 연결합니다.").className = "notice-text";
  section.append(card);
  main.append(section);
  fragment.append(main);
  appRoot.replaceChildren(fragment);
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
}

window.addEventListener("hashchange", render);
render();
