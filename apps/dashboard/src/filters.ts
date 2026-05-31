type RuleOrigin = "built_in" | "custom";
type RuleKind = "detector" | "keyword" | "regex" | "context_rule";
type RuleSeverity = "low" | "medium" | "high" | "critical";
type RuleAction = "ALLOW" | "WARN" | "MASK" | "BLOCK";

type FilterRule = {
  id: string;
  origin: RuleOrigin;
  kind: RuleKind;
  category: string;
  label: string;
  description: string | null;
  placeholder: string | null;
  severity: RuleSeverity;
  action: RuleAction;
  enabled: boolean;
  editable_fields: Record<string, boolean>;
  config_json: Record<string, unknown> | null;
  created_at: string | null;
  updated_at: string | null;
  archived_at: string | null;
};

type FilterFormState = {
  mode: "create" | "edit";
  id: string | null;
  origin: RuleOrigin;
  kind: RuleKind;
  category: string;
  label: string;
  description: string;
  placeholder: string;
  severity: RuleSeverity;
  action: RuleAction;
  enabled: boolean;
  keywords: string;
  exclusionKeywords: string;
  pattern: string;
  contextGroups: string;
  windowSize: string;
  minConditionCount: string;
  sensitivity: "low" | "medium" | "high";
};

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
const apiBaseUrl = document.documentElement.dataset.promptguardApiBaseUrl ?? "http://localhost:8000";

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

function splitCsv(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function contextGroupConfig(value: string): Record<string, string[]> {
  const groups: Record<string, string[]> = {};
  for (const line of value.split("\n")) {
    const [name, terms] = line.split(":");
    if (!name || !terms) continue;
    const items = splitCsv(terms);
    if (items.length > 0) groups[name.trim()] = items;
  }
  return groups;
}

function configFromForm(state: FilterFormState): Record<string, unknown> {
  if (state.kind === "keyword") {
    return {
      keywords: splitCsv(state.keywords),
      exclusion_keywords: splitCsv(state.exclusionKeywords),
    };
  }
  if (state.kind === "regex") {
    return {
      pattern: state.pattern.trim(),
      exclusion_keywords: splitCsv(state.exclusionKeywords),
    };
  }
  return {
    keyword_groups: contextGroupConfig(state.contextGroups),
    exclusion_keywords: splitCsv(state.exclusionKeywords),
    window_size: Number(state.windowSize),
    min_condition_count: Number(state.minConditionCount),
    sensitivity: state.sensitivity,
  };
}

function payloadFromForm(state: FilterFormState): Record<string, unknown> {
  const config = configFromForm(state);
  const payload: Record<string, unknown> = {
    category: state.category.trim(),
    label: state.label.trim(),
    description: state.description.trim() || null,
    placeholder: state.placeholder.trim() || null,
    severity: state.severity,
    action: state.action,
    enabled: state.enabled,
    config_json: config,
  };
  if (state.kind === "keyword") {
    payload.kind = "keyword";
    payload.keyword = splitCsv(state.keywords)[0] ?? "";
  }
  if (state.kind === "regex") {
    payload.kind = "regex";
    payload.pattern = state.pattern.trim();
  }
  if (state.kind === "context_rule") {
    payload.kind = "context_rule";
  }
  return payload;
}

async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error("요청을 완료하지 못했습니다.");
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
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
    pageMessage = "Filter Rule 정보를 불러오지 못했습니다. 관리자 세션이 필요하거나 서버 연결을 확인해야 합니다.";
  }
  render();
}

async function saveRule(): Promise<void> {
  const payload = payloadFromForm(formState);
  if (formState.mode === "create") {
    await apiRequest<FilterRule>("/dashboard/filters", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } else if (formState.id) {
    const updatePayload = formState.origin === "built_in"
      ? {
          severity: formState.severity,
          action: formState.action,
          enabled: formState.enabled,
        }
      : payload;
    await apiRequest<FilterRule>(`/dashboard/filters/${formState.id}`, {
      method: "PATCH",
      body: JSON.stringify(updatePayload),
    });
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
  const payload: Record<string, unknown> = {
    sample_text: dryRunText,
  };
  if (formState.mode === "edit" && formState.id) {
    payload.rule_id = formState.id;
  } else {
    payload.draft_rule = payloadFromForm(formState);
  }
  dryRunResult = await apiRequest<DryRunResult>("/dashboard/filters/dry-run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  render();
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function button(label: string, className: string, onClick: () => void, disabled = false): HTMLButtonElement {
  const node = el("button", className, label);
  node.type = "button";
  node.disabled = disabled;
  node.addEventListener("click", onClick);
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
  copy.append(el("p", "eyebrow", "PromptGuard Dashboard"), el("h1", undefined, "Filter Rule 관리"), el("p", "header-desc", "built-in detector와 custom rule을 한 화면에서 관리합니다."));
  const nav = el("nav", "header-actions");
  const overview = el("a", "nav-button", "대시보드");
  overview.href = "admin.html";
  const events = el("a", "nav-button", "이벤트 관리");
  events.href = "events.html";
  const users = el("a", "nav-button", "사용자 관리");
  users.href = "users.html";
  const filters = el("a", "nav-button active", "필터 관리");
  filters.href = "filters.html";
  const logout = el("a", "logout-button", "로그아웃");
  logout.href = "index.html";
  nav.append(overview, events, users, filters, logout);
  header.append(copy, nav);
  return header;
}

function renderSummary(): HTMLElement {
  const summary = el("section", "filter-summary");
  const builtIn = rules.filter((rule) => rule.origin === "built_in").length;
  const custom = rules.filter((rule) => rule.origin === "custom").length;
  summary.append(
    el("strong", undefined, "Filter Rule 설정 요약"),
    el("p", undefined, `built-in ${builtIn}개, custom ${custom}개가 현재 관리 대상입니다. dry-run은 저장 없이 단일 rule의 예상 결과만 확인합니다.`),
  );
  return summary;
}

function renderRuleTable(): HTMLElement {
  const card = el("section", "table-card");
  const table = el("table", "data-table filter-table");
  const thead = el("thead");
  const headRow = el("tr");
  ["Origin", "Kind", "Rule", "Severity", "Action", "Enabled", "Controls"].forEach((title) => headRow.append(el("th", undefined, title)));
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
    button("Edit", "text-action", () => {
      selectedRuleId = rule.id;
      formState = formFromRule(rule);
      dryRunResult = null;
      render();
    }),
    button(rule.enabled ? "Disable" : "Enable", "text-action", () => void setRuleEnabled(rule, !rule.enabled)),
    button("Archive", "text-action danger-text", () => void archiveRule(rule), rule.origin === "built_in"),
  );
  return cell;
}

function renderForm(): HTMLElement {
  const card = el("section", "filter-card");
  const header = el("div", "filter-card-header");
  const copy = el("div");
  copy.append(el("h2", undefined, formState.mode === "create" ? "Custom Rule 생성" : "Rule 수정"), el("p", undefined, "kind별 필드로 설정을 편집합니다."));
  header.append(copy, button("New Custom", "nav-button", () => {
    selectedRuleId = null;
    formState = blankForm();
    dryRunResult = null;
    render();
  }));
  const form = el("form", "filter-form");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void saveRule().catch(() => {
      pageMessage = "저장을 완료하지 못했습니다. 입력값과 관리자 권한을 확인하세요.";
      render();
    });
  });
  const builtIn = formState.origin === "built_in";
  const canEditMeta = !builtIn;
  const row1 = el("div", "form-row three");
  row1.append(
    field("Kind", select(formState.kind, ["keyword", "regex", "context_rule"] as RuleKind[], (value) => {
      formState.kind = value;
      render();
    }, formState.mode === "edit")),
    field("Category", input(formState.category, (value) => { formState.category = value; }, !canEditMeta)),
    field("Enabled", checkbox(formState.enabled, (value) => { formState.enabled = value; })),
  );
  const row2 = el("div", "form-row");
  row2.append(
    field("Label", input(formState.label, (value) => { formState.label = value; }, !canEditMeta)),
    field("Placeholder", input(formState.placeholder, (value) => { formState.placeholder = value; }, !canEditMeta)),
  );
  const row3 = el("div", "form-row");
  row3.append(
    field("Severity", select(formState.severity, ["low", "medium", "high", "critical"] as RuleSeverity[], (value) => { formState.severity = value; })),
    field("Action", select(formState.action, ["ALLOW", "WARN", "MASK", "BLOCK"] as RuleAction[], (value) => { formState.action = value; })),
  );
  form.append(header, row1, row2, row3, field("Description", textarea(formState.description, (value) => { formState.description = value; }, !canEditMeta)));
  if (!builtIn) {
    form.append(renderKindFields());
  }
  const actions = el("div", "form-actions");
  actions.append(button("Save", "login-button", () => undefined), button("Run dry-run", "nav-button", () => void runDryRun().catch(() => {
    pageMessage = "dry-run을 완료하지 못했습니다. sample과 rule 설정을 확인하세요.";
    render();
  }), !dryRunText.trim()));
  form.append(actions);
  card.append(form);
  return card;
}

function renderKindFields(): HTMLElement {
  const box = el("div", "context-box");
  if (formState.kind === "keyword") {
    const row = el("div", "form-row");
    row.append(
      field("Keywords", input(formState.keywords, (value) => { formState.keywords = value; })),
      field("Exclusion Keywords", input(formState.exclusionKeywords, (value) => { formState.exclusionKeywords = value; })),
    );
    box.append(el("h3", undefined, "Keyword 설정"), row);
  } else if (formState.kind === "regex") {
    const row = el("div", "form-row");
    row.append(
      field("Pattern", input(formState.pattern, (value) => { formState.pattern = value; })),
      field("Exclusion Keywords", input(formState.exclusionKeywords, (value) => { formState.exclusionKeywords = value; })),
    );
    box.append(el("h3", undefined, "Regex 설정"), row);
  } else {
    const row = el("div", "form-row three");
    row.append(
      field("Window Size", input(formState.windowSize, (value) => { formState.windowSize = value; })),
      field("Min Conditions", input(formState.minConditionCount, (value) => { formState.minConditionCount = value; })),
      field("Sensitivity", select(formState.sensitivity, ["low", "medium", "high"], (value) => { formState.sensitivity = value; })),
    );
    box.append(
      el("h3", undefined, "Context Rule 설정"),
      field("Keyword Groups", textarea(formState.contextGroups, (value) => { formState.contextGroups = value; })),
      field("Exclusion Keywords", input(formState.exclusionKeywords, (value) => { formState.exclusionKeywords = value; })),
      row,
    );
  }
  return box;
}

function renderDryRun(): HTMLElement {
  const card = el("section", "filter-card dryrun-card");
  card.append(el("h2", undefined, "Dry-run"), el("p", "filter-subtext", "샘플은 저장하지 않고 안전한 metadata만 표시합니다."));
  const sample = textarea(dryRunText, (value) => { dryRunText = value; });
  sample.className = "dryrun-textarea";
  card.append(field("Sample", sample));
  const result = el("div", "dryrun-result");
  result.append(el("h3", undefined, "Result"));
  if (!dryRunResult) {
    result.append(el("p", "empty-state", "아직 실행된 결과가 없습니다."));
  } else {
    const keywords = dryRunResult.matched_keywords.length > 0 ? dryRunResult.matched_keywords.join(", ") : "none";
    [
      ["matched", String(dryRunResult.matched)],
      ["expected_action", dryRunResult.expected_action],
      ["expected_severity", dryRunResult.expected_severity],
      ["match_count", String(dryRunResult.match_count)],
      ["reason_code", dryRunResult.reason_code],
      ["matched_keywords", keywords],
      ["sample_persisted", String(dryRunResult.sample_persisted)],
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
    main.append(el("section", "filter-summary", "Filter Rules를 불러오는 중입니다."));
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
    main.append(el("section", "table-card empty-state", "표시할 Filter Rule이 없습니다."));
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
