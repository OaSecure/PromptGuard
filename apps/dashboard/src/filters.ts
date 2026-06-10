import { DashboardApiError, dashboardRequest } from "./dashboardApi.js";
import {
  buildFilterDryRunPayload,
  buildFilterMutationPayload,
  filterFormActionSpecs,
  filterHeaderNavItems,
  safeFilterMutationErrorMessage,
  type FilterFormState,
  type FilterRule,
  type RuleAction,
  type RuleKind,
  type RuleSeverity,
} from "./filtersPageModel.js";
import { logoutDashboardSession, refreshDashboardCsrf } from "./session.js";

type DryRunResult = {
  matched: boolean;
  expected_action: string;
  expected_severity: string;
  match_count: number;
  reason_code: string;
  matched_keywords: string[];
  evidence_counts: Record<string, number>;
  sample_persisted: boolean;
};

const root = document.querySelector<HTMLDivElement>("#filters-app");

let rules: FilterRule[] = [];
let selectedRuleId: string | null = null;
let formState: FilterFormState = blankForm();
let dryRunText = "";
let dryRunResult: DryRunResult | null = null;
let pageState: "loading" | "loaded" | "empty" | "error" = "loading";
let pageMessage = "";

function blankForm(): FilterFormState {
  return {
    mode: "create",
    id: null,
    origin: "custom",
    kind: "keyword",
    category: "Custom",
    label: "",
    description: "",
    placeholder: "CUSTOM_KEYWORD",
    severity: "medium",
    action: "MASK",
    enabled: true,
    keywords: "",
    exclusionKeywords: "",
    pattern: "",
    contextGroups: "business: internal strategy",
    windowSize: "80",
    minConditionCount: "1",
    sensitivity: "medium",
  };
}

function textList(value: unknown): string {
  if (!Array.isArray(value)) return "";
  return value.filter((item): item is string => typeof item === "string").join(", ");
}

function formFromRule(rule: FilterRule): FilterFormState {
  const config = rule.config_json ?? {};
  const groups = config.keyword_groups;
  const contextGroups =
    groups && typeof groups === "object" && !Array.isArray(groups)
      ? Object.entries(groups as Record<string, unknown>)
          .map(([name, values]) => `${name}: ${textList(values)}`)
          .join("\n")
      : "";
  return {
    mode: "edit",
    id: rule.id,
    origin: rule.origin,
    kind: rule.kind,
    category: rule.category,
    label: rule.label,
    description: rule.description ?? "",
    placeholder: rule.placeholder ?? "",
    severity: rule.severity,
    action: rule.action,
    enabled: rule.enabled,
    keywords: textList(config.keywords) || "",
    exclusionKeywords: textList(config.exclusion_keywords),
    pattern: typeof config.pattern === "string" ? config.pattern : "",
    contextGroups,
    windowSize: typeof config.window_size === "number" ? String(config.window_size) : "80",
    minConditionCount: typeof config.min_condition_count === "number" ? String(config.min_condition_count) : "1",
    sensitivity: config.sensitivity === "low" || config.sensitivity === "high" ? config.sensitivity : "medium",
  };
}

async function apiRequest<T>(
  path: string,
  options: { method?: "GET" | "POST" | "PATCH" | "DELETE"; body?: unknown } = {},
): Promise<T> {
  const csrfToken = options.method && options.method !== "GET" ? await refreshDashboardCsrf() : null;
  return dashboardRequest<T>(path, {
    ...options,
    csrfToken,
  });
}

async function loadRules(): Promise<void> {
  pageState = "loading";
  pageMessage = "";
  render();
  try {
    rules = await apiRequest<FilterRule[]>("/dashboard/filters");
    pageState = rules.length > 0 ? "loaded" : "empty";
    if (!selectedRuleId && rules.length > 0) {
      selectedRuleId = rules[0].id;
      formState = formFromRule(rules[0]);
    }
  } catch {
    rules = [];
    selectedRuleId = null;
    formState = blankForm();
    pageState = "error";
    pageMessage = "필터 규칙 정보를 불러오지 못했습니다. 관리자 세션이 필요하거나 서버 연결을 확인해야 합니다.";
  }
  render();
}

async function saveRule(): Promise<void> {
  const payload = buildFilterMutationPayload(formState);
  if (formState.mode === "create") {
    await apiRequest<FilterRule>("/dashboard/filters", {
      method: "POST",
      body: payload,
    });
  } else if (formState.id) {
    await apiRequest<FilterRule>(`/dashboard/filters/${formState.id}`, { method: "PATCH", body: payload });
  }
  dryRunResult = null;
  await loadRules();
}

async function setRuleEnabled(rule: FilterRule, enabled: boolean): Promise<void> {
  await apiRequest<FilterRule>(`/dashboard/filters/${rule.id}/${enabled ? "enable" : "disable"}`, { method: "PATCH" });
  await loadRules();
}

async function archiveRule(rule: FilterRule): Promise<void> {
  if (rule.origin === "built_in") return;
  await apiRequest<void>(`/dashboard/filters/${rule.id}`, { method: "DELETE" });
  selectedRuleId = null;
  formState = blankForm();
  await loadRules();
}

async function runDryRun(): Promise<void> {
  const payload = buildFilterDryRunPayload(formState, dryRunText);
  dryRunResult = await apiRequest<DryRunResult>("/dashboard/filters/dry-run", {
    method: "POST",
    body: payload,
  });
  render();
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function apiStatus(error: unknown): number {
  return error instanceof DashboardApiError ? error.status : 0;
}

function button(
  label: string,
  className: string,
  onClick?: () => void,
  disabled = false,
  type: "button" | "submit" = "button",
): HTMLButtonElement {
  const node = el("button", className, label);
  node.type = type;
  node.disabled = disabled;
  if (onClick) node.addEventListener("click", onClick);
  return node;
}

function field(label: string, control: HTMLElement): HTMLLabelElement {
  const wrapper = el("label");
  wrapper.append(label, control);
  return wrapper;
}

function input(value: string, onInput: (value: string) => void, disabled = false): HTMLInputElement {
  const node = el("input");
  node.value = value;
  node.disabled = disabled;
  node.addEventListener("input", () => onInput(node.value));
  return node;
}

function textarea(value: string, onInput: (value: string) => void, disabled = false): HTMLTextAreaElement {
  const node = el("textarea");
  node.value = value;
  node.disabled = disabled;
  node.addEventListener("input", () => onInput(node.value));
  return node;
}

function select<T extends string>(value: T, values: T[], onChange: (value: T) => void, disabled = false): HTMLSelectElement {
  const node = el("select");
  for (const item of values) {
    const option = el("option", undefined, item);
    option.value = item;
    node.append(option);
  }
  node.value = value;
  node.disabled = disabled;
  node.addEventListener("change", () => onChange(node.value as T));
  return node;
}

function checkbox(value: boolean, onChange: (value: boolean) => void, disabled = false): HTMLInputElement {
  const node = el("input");
  node.type = "checkbox";
  node.checked = value;
  node.disabled = disabled;
  node.addEventListener("change", () => onChange(node.checked));
  return node;
}

function renderHeader(): HTMLElement {
  const header = el("header", "admin-header");
  const copy = el("div");
  copy.append(el("p", "eyebrow", "OASecure 필터 관리"), el("h1", undefined, "필터 관리"), el("p", "header-desc", "기본 탐지 규칙과 사용자 정의 규칙을 한 화면에서 관리합니다."));
  const nav = el("nav", "header-actions");
  for (const item of filterHeaderNavItems()) {
    const link = el("a", item.className, item.label);
    link.href = item.href;
    if (item.requiresSessionLogout) {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        void logoutDashboardSession().finally(() => {
          window.location.href = item.href;
        });
      });
    }
    nav.append(link);
  }
  header.append(copy, nav);
  return header;
}

function renderSummary(): HTMLElement {
  const summary = el("section", "filter-summary");
  const builtIn = rules.filter((rule) => rule.origin === "built_in").length;
  const custom = rules.filter((rule) => rule.origin === "custom").length;
  summary.append(
    el("strong", undefined, "필터 규칙 설정 요약"),
    el("p", undefined, `기본 규칙 ${builtIn}개, 사용자 정의 규칙 ${custom}개가 현재 관리 대상입니다. 미리 실행은 저장 없이 단일 규칙의 예상 결과만 확인합니다.`),
  );
  return summary;
}

function renderRuleTable(): HTMLElement {
  const card = el("section", "table-card");
  const table = el("table", "data-table filter-table");
  const thead = el("thead");
  const headRow = el("tr");
  ["출처", "종류", "규칙", "심각도", "처리", "활성화", "관리"].forEach((title) => headRow.append(el("th", undefined, title)));
  thead.append(headRow);
  const tbody = el("tbody");
  for (const rule of rules) {
    const row = el("tr");
    row.append(
      cellBadge(rule.origin, "source-badge"),
      el("td", undefined, rule.kind),
      ruleNameCell(rule),
      cellBadge(rule.severity, "severity-badge"),
      el("td", undefined, rule.action),
      el("td", undefined, rule.enabled ? "ON" : "OFF"),
      ruleActionCell(rule),
    );
    row.addEventListener("click", () => {
      selectedRuleId = rule.id;
      formState = formFromRule(rule);
      dryRunResult = null;
      render();
    });
    tbody.append(row);
  }
  table.append(thead, tbody);
  card.append(table);
  return card;
}

function ruleNameCell(rule: FilterRule): HTMLTableCellElement {
  const cell = el("td");
  cell.append(document.createTextNode(rule.label));
  if (rule.description) cell.append(el("small", undefined, rule.description));
  return cell;
}

function cellBadge(value: string, className: string): HTMLTableCellElement {
  const cell = el("td");
  cell.append(el("span", `${className} ${value}`, value));
  return cell;
}

function ruleActionCell(rule: FilterRule): HTMLTableCellElement {
  const cell = el("td");
  cell.append(
    button("수정", "text-action", () => {
      selectedRuleId = rule.id;
      formState = formFromRule(rule);
      dryRunResult = null;
      render();
    }),
    button(rule.enabled ? "비활성화" : "활성화", "text-action", () => void setRuleEnabled(rule, !rule.enabled)),
    button("보관", "text-action danger-text", () => void archiveRule(rule), rule.origin === "built_in"),
  );
  return cell;
}

function renderForm(): HTMLElement {
  const card = el("section", "filter-card");
  const header = el("div", "filter-card-header");
  const copy = el("div");
  copy.append(el("h2", undefined, formState.mode === "create" ? "사용자 정의 규칙 생성" : "규칙 수정"), el("p", undefined, "종류별 필드로 설정을 편집합니다."));
  header.append(copy, button("사용자 정의 새로 만들기", "nav-button", () => {
    selectedRuleId = null;
    formState = blankForm();
    dryRunResult = null;
    render();
  }));
  const form = el("form", "filter-form");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void saveRule().catch((error: unknown) => {
      pageMessage = safeFilterMutationErrorMessage(apiStatus(error), error);
      render();
    });
  });
  const builtIn = formState.origin === "built_in";
  const canEditMeta = !builtIn;
  const row1 = el("div", "form-row three");
  row1.append(
    field("종류", select(formState.kind, ["keyword", "regex", "context_rule"] as RuleKind[], (value) => {
      formState.kind = value;
      render();
    }, formState.mode === "edit")),
    field("카테고리", input(formState.category, (value) => { formState.category = value; }, !canEditMeta)),
    field("활성화", checkbox(formState.enabled, (value) => { formState.enabled = value; })),
  );
  const row2 = el("div", "form-row");
  row2.append(
    field("라벨", input(formState.label, (value) => { formState.label = value; }, !canEditMeta)),
    field("치환 표시", input(formState.placeholder, (value) => { formState.placeholder = value; }, !canEditMeta)),
  );
  const row3 = el("div", "form-row");
  row3.append(
    field("심각도", select(formState.severity, ["low", "medium", "high", "critical"] as RuleSeverity[], (value) => { formState.severity = value; })),
    field("처리", select(formState.action, ["ALLOW", "WARN", "MASK", "BLOCK"] as RuleAction[], (value) => { formState.action = value; })),
  );
  form.append(header, row1, row2, row3, field("설명", textarea(formState.description, (value) => { formState.description = value; }, !canEditMeta)));
  if (!builtIn) {
    form.append(renderKindFields());
  }
  const actions = el("div", "form-actions");
  const [saveAction, dryRunAction] = filterFormActionSpecs(Boolean(dryRunText.trim()));
  actions.append(
    button(saveAction.label, "login-button", undefined, saveAction.disabled, saveAction.type),
    button(dryRunAction.label, "nav-button", () => void runDryRun().catch((error: unknown) => {
      pageMessage = safeFilterMutationErrorMessage(apiStatus(error), error);
      render();
    }), dryRunAction.disabled, dryRunAction.type),
  );
  form.append(actions);
  card.append(form);
  return card;
}

function renderKindFields(): HTMLElement {
  const box = el("div", "context-box");
  if (formState.kind === "keyword") {
    const row = el("div", "form-row");
    row.append(
      field("키워드", input(formState.keywords, (value) => { formState.keywords = value; })),
      field("제외 키워드", input(formState.exclusionKeywords, (value) => { formState.exclusionKeywords = value; })),
    );
    box.append(el("h3", undefined, "키워드 설정"), row);
  } else if (formState.kind === "regex") {
    const row = el("div", "form-row");
    row.append(
      field("패턴", input(formState.pattern, (value) => { formState.pattern = value; })),
      field("제외 키워드", input(formState.exclusionKeywords, (value) => { formState.exclusionKeywords = value; })),
    );
    box.append(el("h3", undefined, "정규식 설정"), row);
  } else {
    const row = el("div", "form-row three");
    row.append(
      field("검사 범위", input(formState.windowSize, (value) => { formState.windowSize = value; })),
      field("최소 조건 수", input(formState.minConditionCount, (value) => { formState.minConditionCount = value; })),
      field("민감도", select(formState.sensitivity, ["low", "medium", "high"], (value) => { formState.sensitivity = value; })),
    );
    box.append(
      el("h3", undefined, "업무 맥락 규칙 설정"),
      field("키워드 그룹", textarea(formState.contextGroups, (value) => { formState.contextGroups = value; })),
      field("제외 키워드", input(formState.exclusionKeywords, (value) => { formState.exclusionKeywords = value; })),
      row,
    );
  }
  return box;
}

function renderDryRun(): HTMLElement {
  const card = el("section", "filter-card dryrun-card");
  card.append(el("h2", undefined, "미리 실행"), el("p", "filter-subtext", "샘플은 저장하지 않고 안전한 메타데이터만 표시합니다."));
  const sample = textarea(dryRunText, (value) => { dryRunText = value; });
  sample.className = "dryrun-textarea";
  card.append(field("샘플", sample));
  const result = el("div", "dryrun-result");
  result.append(el("h3", undefined, "결과"));
  if (!dryRunResult) {
    result.append(el("p", "empty-state", "아직 실행된 결과가 없습니다."));
  } else {
    const keywords = dryRunResult.matched_keywords.length > 0 ? dryRunResult.matched_keywords.join(", ") : "없음";
    [
      ["일치 여부", String(dryRunResult.matched)],
      ["예상 처리", dryRunResult.expected_action],
      ["예상 심각도", dryRunResult.expected_severity],
      ["일치 수", String(dryRunResult.match_count)],
      ["사유 코드", dryRunResult.reason_code],
      ["일치 키워드", keywords],
      ["샘플 저장 여부", String(dryRunResult.sample_persisted)],
    ].forEach(([name, value]) => {
      const row = el("div", "result-row");
      row.append(el("span", undefined, name), el("strong", undefined, value));
      result.append(row);
    });
  }
  card.append(result);
  return card;
}

function renderMain(): HTMLElement {
  const main = el("main", "dashboard filter-dashboard");
  if (pageMessage) main.append(el("p", "privacy-note", pageMessage));
  if (pageState === "loading") {
    main.append(el("section", "filter-summary", "필터 규칙을 불러오는 중입니다."));
    return main;
  }
  if (pageState === "error") {
    main.append(el("section", "filter-summary", "안전한 fallback 상태입니다. 서버 연결 후 다시 시도하세요."));
    return main;
  }
  main.append(renderSummary());
  const grid = el("section", "filter-grid");
  grid.append(renderForm(), renderDryRun());
  main.append(grid);
  if (pageState === "empty") {
    main.append(el("section", "table-card empty-state", "표시할 필터 규칙이 없습니다."));
  } else {
    main.append(renderRuleTable());
  }
  return main;
}

function render(): void {
  if (!root) return;
  root.replaceChildren(renderHeader(), renderMain());
}

render();
void loadRules();
