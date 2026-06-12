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

export type FilterSelectOption<TValue extends string> = {
  value: TValue;
  label: string;
};

export type FilterSavePlan =
  | { kind: "validation_error"; errors: FilterValidationError[] }
  | { kind: "request"; path: string; method: "POST" | "PATCH"; body: Record<string, unknown> };

export type FilterDryRunPlan =
  | { kind: "validation_error"; errors: FilterValidationError[] }
  | { kind: "request"; path: "/dashboard/filters/dry-run"; method: "POST"; body: Record<string, unknown> };

export type FilterFieldVisibility = {
  canEditIdentity: boolean;
  showPlaceholder: boolean;
  showKeywordFields: boolean;
  showRegexFields: boolean;
  showContextFields: boolean;
};

export type FilterValidationError = {
  field: "label" | "keywords" | "pattern" | "contextGroups" | "sampleText" | "windowSize" | "minConditionCount";
  message: string;
};

const MAX_REGEX_PATTERN_LENGTH = 1000;

export function filterRegexHelpText(): string {
  return "Python 정규식 패턴만 입력합니다. 예: secret-[0-9]+, api[_-]?key. 슬래시(/.../)는 쓰지 않고 저장 또는 미리 실행 시 서버가 문법을 검증합니다.";
}

export function filterDryRunHelpText(): string {
  return "현재 작성 중인 규칙을 서버의 실제 필터 엔진으로 실행합니다. 샘플은 저장하지 않고 일치 여부, 예상 처리, 예상 심각도 같은 안전한 메타데이터만 반환합니다.";
}

export function filterKindOptions(): FilterSelectOption<RuleKind>[] {
  return [
    { value: "keyword", label: "키워드" },
    { value: "regex", label: "정규식" },
    { value: "context_rule", label: "업무 맥락" },
  ];
}

export function filterSeverityOptions(): FilterSelectOption<RuleSeverity>[] {
  return [
    { value: "low", label: "낮음" },
    { value: "medium", label: "보통" },
    { value: "high", label: "높음" },
    { value: "critical", label: "심각" },
  ];
}

export function filterActionOptions(): FilterSelectOption<RuleAction>[] {
  return [
    { value: "ALLOW", label: "허용" },
    { value: "WARN", label: "경고" },
    { value: "MASK", label: "마스킹" },
    { value: "BLOCK", label: "차단" },
  ];
}

export function filterSensitivityOptions(): FilterSelectOption<"low" | "medium" | "high">[] {
  return [
    { value: "low", label: "낮음" },
    { value: "medium", label: "보통" },
    { value: "high", label: "높음" },
  ];
}

export function filterFieldVisibility(state: FilterFormState): FilterFieldVisibility {
  const canEditIdentity = state.origin !== "built_in";
  return {
    canEditIdentity,
    showPlaceholder: canEditIdentity && state.action === "MASK",
    showKeywordFields: canEditIdentity && state.kind === "keyword",
    showRegexFields: canEditIdentity && state.kind === "regex",
    showContextFields: canEditIdentity && state.kind === "context_rule",
  };
}

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

export function validateFilterFormState(state: FilterFormState): FilterValidationError[] {
  if (!state.label.trim()) {
    return [{ field: "label", message: "규칙 이름을 입력해 주세요." }];
  }
  if (state.kind === "keyword" && splitCsv(state.keywords).length === 0) {
    return [{ field: "keywords", message: "키워드를 하나 이상 입력해 주세요." }];
  }
  if (state.kind === "regex" && !state.pattern.trim()) {
    return [{ field: "pattern", message: "정규식 패턴을 입력해 주세요." }];
  }
  if (state.kind === "regex" && state.pattern.trim().length > MAX_REGEX_PATTERN_LENGTH) {
    return [{ field: "pattern", message: "정규식 패턴은 1000자 이하로 입력해 주세요." }];
  }
  if (state.kind === "context_rule" && Object.keys(contextGroupConfig(state.contextGroups)).length === 0) {
    return [{ field: "contextGroups", message: "업무 맥락 그룹을 '그룹명: 키워드1, 키워드2' 형식으로 입력해 주세요." }];
  }
  if (state.kind === "context_rule" && !isPositiveInteger(state.windowSize)) {
    return [{ field: "windowSize", message: "검사 범위는 1 이상의 정수로 입력해 주세요." }];
  }
  if (state.kind === "context_rule" && !isPositiveInteger(state.minConditionCount)) {
    return [{ field: "minConditionCount", message: "최소 조건 수는 1 이상의 정수로 입력해 주세요." }];
  }
  return [];
}

export function buildFilterSavePlan(state: FilterFormState): FilterSavePlan {
  const errors = validateFilterFormState(state);
  if (errors.length > 0) {
    return { kind: "validation_error", errors };
  }
  const body = buildFilterMutationPayload(state);
  if (state.mode === "edit" && state.id) {
    return { kind: "request", path: `/dashboard/filters/${state.id}`, method: "PATCH", body };
  }
  return { kind: "request", path: "/dashboard/filters", method: "POST", body };
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
    placeholder: state.action === "MASK" ? state.placeholder.trim() || null : null,
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

export function buildFilterDryRunPlan(state: FilterFormState, sampleText: string): FilterDryRunPlan {
  if (!sampleText.trim()) {
    return {
      kind: "validation_error",
      errors: [{ field: "sampleText", message: "미리 실행할 샘플을 입력해 주세요." }],
    };
  }
  const errors = validateFilterFormState(state);
  if (errors.length > 0) {
    return { kind: "validation_error", errors };
  }
  return {
    kind: "request",
    path: "/dashboard/filters/dry-run",
    method: "POST",
    body: buildFilterDryRunPayload(state, sampleText),
  };
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

function isPositiveInteger(value: string): boolean {
  if (!/^[0-9]+$/.test(value.trim())) return false;
  return Number(value) > 0;
}
