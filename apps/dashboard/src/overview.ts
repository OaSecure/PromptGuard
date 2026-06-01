import { DashboardApiError, dashboardRequest } from "./dashboardApi.js";
import { logoutDashboardSession } from "./session.js";

type CountRow<T extends string> = Record<T, string> & {
  count: number;
};

type PeriodBucket = {
  bucket_start: string;
  bucket_end: string;
  event_count: number;
  blocked_count: number;
  masked_count: number;
  warned_count: number;
};

type DashboardOverview = {
  period_start: string;
  period_end: string;
  event_count: number;
  blocked_count: number;
  masked_count: number;
  warned_count: number;
  allowed_count: number;
  active_user_count: number;
  content_unavailable_event_count: number;
  last_event_at: string | null;
  action_counts: Array<CountRow<"action">>;
  risk_level_counts: Array<CountRow<"risk_level">>;
  detector_category_counts: Array<CountRow<"category">>;
  period_buckets: PeriodBucket[];
};

const message = requireElement<HTMLElement>("overview-message");
const cards = requireElement<HTMLElement>("overview-cards");
const periodLabel = requireElement<HTMLElement>("overview-period");
const actionCounts = requireElement<HTMLElement>("action-counts");
const riskLevelCounts = requireElement<HTMLOListElement>("risk-level-counts");
const detectorCategoryCounts = requireElement<HTMLOListElement>("detector-category-counts");
const periodBuckets = requireElement<HTMLElement>("period-buckets");
const valueTargets = new Map(
  Array.from(document.querySelectorAll<HTMLElement>("[data-overview-value]")).map((element) => [
    element.dataset.overviewValue ?? "",
    element,
  ]),
);

function requireElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) {
    throw new Error(`Missing dashboard element: ${id}`);
  }
  return element as T;
}

function setMessage(text: string, kind: "loading" | "empty" | "error" | "ready"): void {
  message.textContent = text;
  message.hidden = kind === "ready";
  message.setAttribute("role", kind === "error" ? "alert" : "status");
  message.setAttribute("aria-live", kind === "error" ? "assertive" : "polite");
}

function setMetric(key: keyof DashboardOverview, value: string): void {
  const target = valueTargets.get(key);
  if (target) {
    target.textContent = value;
  }
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatDateTime(value: string | null): string {
  if (!value) return "None";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "None";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatPeriodDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "2-digit" }).format(date);
}

function barClassForAction(action: string): string {
  if (action === "block") return "blocked";
  if (action === "mask") return "masked";
  if (action === "warn") return "warned";
  return "";
}

function renderActionCounts(rows: Array<CountRow<"action">>): void {
  const maxCount = Math.max(1, ...rows.map((row) => row.count));
  actionCounts.replaceChildren(
    ...rows.map((row) => {
      const item = document.createElement("div");
      item.className = "bar-row";

      const label = document.createElement("span");
      label.textContent = row.action;

      const track = document.createElement("div");
      track.className = "bar-track";

      const fill = document.createElement("i");
      fill.className = `bar-fill ${barClassForAction(row.action)}`.trim();
      fill.style.width = `${Math.max(4, Math.round((row.count / maxCount) * 100))}%`;
      track.append(fill);

      const value = document.createElement("strong");
      value.textContent = formatNumber(row.count);

      item.append(label, track, value);
      return item;
    }),
  );
}

function renderList<T extends string>(
  container: HTMLOListElement,
  rows: Array<CountRow<T>>,
  key: T,
  emptyText: string,
): void {
  if (rows.length === 0) {
    const empty = document.createElement("li");
    empty.textContent = emptyText;
    container.replaceChildren(empty);
    return;
  }

  container.replaceChildren(
    ...rows.map((row, index) => {
      const item = document.createElement("li");
      item.style.setProperty("--slice-color", ["#2f80ed", "#27ae60", "#f2994a", "#9b51e0"][index % 4]);

      const label = document.createElement("span");
      label.textContent = row[key];

      const value = document.createElement("strong");
      value.textContent = formatNumber(row.count);

      item.append(label, value);
      return item;
    }),
  );
}

function renderPeriodBuckets(rows: PeriodBucket[]): void {
  if (rows.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No period data.";
    periodBuckets.replaceChildren(empty);
    return;
  }

  const visibleRows = rows.slice(-14);
  const maxCount = Math.max(1, ...visibleRows.map((row) => row.event_count));
  periodBuckets.replaceChildren(
    ...visibleRows.map((row) => {
      const item = document.createElement("div");
      item.className = "period-column";
      item.title = [
        `Events: ${row.event_count}`,
        `Blocked: ${row.blocked_count}`,
        `Masked: ${row.masked_count}`,
        `Warned: ${row.warned_count}`,
      ].join(" | ");

      const value = document.createElement("strong");
      value.textContent = formatNumber(row.event_count);

      const bar = document.createElement("i");
      bar.style.height = `${Math.max(6, Math.round((row.event_count / maxCount) * 100))}%`;

      const label = document.createElement("span");
      label.textContent = formatPeriodDate(row.bucket_start);

      item.append(value, bar, label);
      return item;
    }),
  );
}

function renderOverview(data: DashboardOverview): void {
  setMetric("event_count", formatNumber(data.event_count));
  setMetric("blocked_count", formatNumber(data.blocked_count));
  setMetric("masked_count", formatNumber(data.masked_count));
  setMetric("warned_count", formatNumber(data.warned_count));
  setMetric("active_user_count", formatNumber(data.active_user_count));
  setMetric("content_unavailable_event_count", formatNumber(data.content_unavailable_event_count));
  setMetric("last_event_at", formatDateTime(data.last_event_at));
  periodLabel.textContent = `${formatPeriodDate(data.period_start)} - ${formatPeriodDate(data.period_end)}`;

  renderActionCounts(data.action_counts);
  renderList(riskLevelCounts, data.risk_level_counts, "risk_level", "No risk data.");
  renderList(detectorCategoryCounts, data.detector_category_counts, "category", "No detector data.");
  renderPeriodBuckets(data.period_buckets);

  cards.setAttribute("aria-busy", "false");
  if (data.event_count === 0) {
    setMessage("No events found for the current period.", "empty");
  } else {
    setMessage("", "ready");
  }
}

function redirectToLogin(): void {
  window.location.href = "./login.html";
}

function safeOverviewErrorMessage(error: unknown): string {
  if (error instanceof DashboardApiError) {
    if (error.status === 401 || error.status === 403) return "Dashboard login is required.";
    if (error.status === 0) return "Dashboard API is unavailable. Try again later.";
  }
  return "Overview data could not be loaded.";
}

async function loadOverview(): Promise<void> {
  cards.setAttribute("aria-busy", "true");
  setMessage("Loading overview summary.", "loading");

  try {
    const data = await dashboardRequest<DashboardOverview>("/dashboard/overview");
    renderOverview(data);
  } catch (error) {
    cards.setAttribute("aria-busy", "false");
    setMessage(safeOverviewErrorMessage(error), "error");
    if (error instanceof DashboardApiError && (error.status === 401 || error.status === 403)) {
      window.setTimeout(redirectToLogin, 700);
    }
  }
}

document.querySelectorAll<HTMLAnchorElement>(".logout-button").forEach((link) => {
  link.addEventListener("click", async (event) => {
    event.preventDefault();
    try {
      await logoutDashboardSession();
    } finally {
      redirectToLogin();
    }
  });
});

void loadOverview();
