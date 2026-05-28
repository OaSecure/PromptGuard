import "./styles/main.css";

type EventAction = "Allowed" | "Warned" | "Masked" | "Blocked";
type RouteId = "overview" | "events" | "users" | "filters" | "status";

type OverviewStat = {
  label: string;
  value: number;
  action?: EventAction;
};

type UserSummary = {
  name: string;
  department: string;
  eventCount: number;
  topSignal: string;
  lastEventAt: string;
};

const routes: Array<{ id: RouteId; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "events", label: "Events" },
  { id: "users", label: "Users" },
  { id: "filters", label: "Filters" },
  { id: "status", label: "Status" }
];

const overviewStats: OverviewStat[] = [
  { label: "Total events", value: 128 },
  { label: "Warned", value: 17, action: "Warned" },
  { label: "Masked", value: 38, action: "Masked" },
  { label: "Blocked", value: 12, action: "Blocked" },
  { label: "Active users", value: 24 }
];

const userSummaries: UserSummary[] = [
  { name: "admin", department: "Security", eventCount: 32, topSignal: "Secret", lastEventAt: "2026-05-26" },
  { name: "user01", department: "Sales", eventCount: 28, topSignal: "Contract", lastEventAt: "2026-05-26" },
  { name: "user02", department: "Ops", eventCount: 21, topSignal: "PII", lastEventAt: "2026-05-25" }
];

const actionTotals: Record<EventAction, number> = {
  Allowed: 61,
  Warned: 17,
  Masked: 38,
  Blocked: 12
};

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

function renderShell(): { nav: HTMLElement; title: HTMLElement; content: HTMLElement; sessionMessage: HTMLElement } {
  const shell = document.createElement("main");
  shell.className = "shell";

  const sidebar = document.createElement("aside");
  sidebar.className = "sidebar";
  sidebar.setAttribute("aria-label", "Dashboard sections");
  appendText(sidebar, "div", "PromptGuard").className = "brand";

  const nav = document.createElement("nav");
  sidebar.append(nav);

  const workspace = document.createElement("section");
  workspace.className = "workspace";

  const topbar = document.createElement("header");
  topbar.className = "topbar";

  const headingGroup = document.createElement("div");
  appendText(headingGroup, "p", "ADMIN dashboard");
  const title = appendText(headingGroup, "h1", "");

  const logoutGroup = document.createElement("div");
  logoutGroup.className = "logout-group";
  const logoutButton = appendText(logoutGroup, "button", "Log out") as HTMLButtonElement;
  logoutButton.type = "button";
  const sessionMessage = appendText(logoutGroup, "span", "");
  sessionMessage.className = "session-message";
  logoutButton.addEventListener("click", () => {
    sessionMessage.textContent = "Logout will call the dashboard session API when auth is connected.";
  });

  topbar.append(headingGroup, logoutGroup);
  const content = document.createElement("section");
  content.className = "content-region";

  workspace.append(topbar, content);
  shell.append(sidebar, workspace);
  app.replaceChildren(shell);

  return { nav, title, content, sessionMessage };
}

function renderNavigation(nav: HTMLElement, activeRoute: RouteId): void {
  nav.replaceChildren();

  for (const route of routes) {
    const link = document.createElement("a");
    link.href = `#${route.id}`;
    link.textContent = route.label;

    if (route.id === activeRoute) {
      link.setAttribute("aria-current", "page");
    }

    nav.append(link);
  }
}

function renderStatCard(stat: OverviewStat): HTMLElement {
  const card = document.createElement("article");
  card.className = stat.action ? `stat-card stat-card--${stat.action.toLowerCase()}` : "stat-card";
  appendText(card, "span", stat.label);
  appendText(card, "strong", String(stat.value));
  return card;
}

function renderActionRow(action: EventAction, total: number): HTMLElement {
  const row = document.createElement("li");
  row.className = "action-row";
  appendText(row, "span", action);

  const max = Math.max(...Object.values(actionTotals));
  const width = Math.max(8, Math.round((total / max) * 100));
  const bar = document.createElement("div");
  bar.className = "bar";
  bar.setAttribute("aria-hidden", "true");
  const fill = document.createElement("i");
  fill.style.width = `${width}%`;
  bar.append(fill);

  appendText(row, "strong", String(total));
  row.insertBefore(bar, row.lastChild);
  return row;
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

function renderOverview(content: HTMLElement): void {
  const stats = document.createElement("section");
  stats.className = "stats";
  stats.setAttribute("aria-label", "Event summary");
  stats.append(...overviewStats.map(renderStatCard));

  const grid = document.createElement("section");
  grid.className = "grid";

  const actionPanel = document.createElement("article");
  actionPanel.className = "panel";
  appendText(actionPanel, "h2", "Action Distribution");
  const actionList = document.createElement("ol");
  actionList.className = "action-list";
  for (const [action, total] of Object.entries(actionTotals) as Array<[EventAction, number]>) {
    actionList.append(renderActionRow(action, total));
  }
  actionPanel.append(actionList);

  const statusPanel = document.createElement("article");
  statusPanel.className = "panel";
  appendText(statusPanel, "h2", "Server Status");
  const statusLine = document.createElement("div");
  statusLine.className = "status-line";
  const statusDot = document.createElement("span");
  statusDot.className = "status-dot";
  appendText(statusLine, "strong", "Ready for dashboard API integration");
  statusLine.prepend(statusDot);
  statusPanel.append(statusLine);
  appendText(statusPanel, "p", "Only metadata summaries are rendered in this scaffold.").className = "muted";

  grid.append(actionPanel, statusPanel);

  const userPanel = document.createElement("section");
  userPanel.className = "panel";
  appendText(userPanel, "h2", "User Event Summary");
  const tableWrap = document.createElement("div");
  tableWrap.className = "table-wrap";
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const heading of ["User", "Department", "Top signal", "Events", "Last event"]) {
    appendText(headRow, "th", heading);
  }
  thead.append(headRow);
  const tbody = document.createElement("tbody");
  tbody.append(...userSummaries.map(renderUserRow));
  table.append(thead, tbody);
  tableWrap.append(table);
  userPanel.append(tableWrap);

  content.replaceChildren(stats, grid, userPanel);
}

function renderPlaceholder(content: HTMLElement, route: Exclude<RouteId, "overview">): void {
  const panel = document.createElement("section");
  panel.className = "panel empty-state";
  appendText(panel, "h2", routes.find((item) => item.id === route)?.label ?? "Dashboard");
  appendText(panel, "p", routePlaceholders[route]).className = "muted";
  content.replaceChildren(panel);
}

const shell = renderShell();

function render(): void {
  const route = currentRoute();
  renderNavigation(shell.nav, route);
  shell.title.textContent = routes.find((item) => item.id === route)?.label ?? "Overview";
  shell.sessionMessage.textContent = "";

  if (route === "overview") {
    renderOverview(shell.content);
    return;
  }

  renderPlaceholder(shell.content, route);
}

window.addEventListener("hashchange", render);
render();
