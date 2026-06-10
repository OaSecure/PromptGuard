export type RuleOrigin = "built_in" | "custom";
export type RuleKind = "detector" | "keyword" | "regex" | "context_rule";
export type RuleSeverity = "low" | "medium" | "high" | "critical";
export type RuleAction = "ALLOW" | "WARN" | "MASK" | "BLOCK";

export type FilterRule = {
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

export type FilterFormState = {
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

export type FilterHeaderNavItem = {
  id: "overview" | "events" | "users" | "filters" | "status" | "logout";
  label: string;
  href: string;
  className: string;
  requiresSessionLogout: boolean;
};

type FilterActionSpec = {
  id: "save" | "dry-run";
  label: string;
  type: "submit" | "button";
  disabled: boolean;
};

export function splitCsv(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function contextGroupConfig(value: string): Record<string, string[]> {
  const groups: Record<string, string[]> = {};
  for (const line of value.split("\n")) {
    const delimiterIndex = line.indexOf(":");
    if (delimiterIndex < 1) continue;
    const name = line.slice(0, delimiterIndex).trim();
    const terms = line.slice(delimiterIndex + 1);
    const items = splitCsv(terms);
    if (name && items.length > 0) groups[name] = items;
  }
  return groups;
}

export function filterFormActionSpecs(canRunDryRun: boolean): FilterActionSpec[] {
  return [
    { id: "save", label: "저장", type: "submit", disabled: false },
    { id: "dry-run", label: "미리 실행", type: "button", disabled: !canRunDryRun },
  ];
}

export function filterHeaderNavItems(): FilterHeaderNavItem[] {
  return [
    { id: "overview", label: "대시보드", href: "overview.html", className: "nav-button", requiresSessionLogout: false },
    { id: "events", label: "이벤트 관리", href: "events.html", className: "nav-button", requiresSessionLogout: false },
    { id: "users", label: "사용자 관리", href: "users.html", className: "nav-button", requiresSessionLogout: false },
    { id: "filters", label: "필터 관리", href: "filters.html", className: "nav-button active", requiresSessionLogout: false },
    { id: "status", label: "서버 상태", href: "status.html", className: "nav-button", requiresSessionLogout: false },
    { id: "logout", label: "로그아웃", href: "login.html", className: "logout-button", requiresSessionLogout: true },
  ];
}

export function buildFilterMutationPayload(state: FilterFormState): Record<string, unknown> {
  if (state.mode === "edit" && state.origin === "built_in") {
    return {
      severity: state.severity,
      action: state.action,
      enabled: state.enabled,
    };
  }

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

export function buildFilterDryRunPayload(state: FilterFormState, sampleText: string): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    sample_text: sampleText,
  };
  if (state.mode === "edit" && state.id) {
    payload.rule_id = state.id;
  } else {
    payload.draft_rule = buildFilterMutationPayload(state);
  }
  return payload;
}

export function safeFilterMutationErrorMessage(status: number, _detail?: unknown): string {
  if (status === 400 || status === 422) return "입력값을 확인해 주세요.";
  if (status === 401 || status === 403) return "대시보드 권한 또는 보안 토큰을 확인할 수 없습니다. 다시 로그인해 주세요.";
  return "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
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
