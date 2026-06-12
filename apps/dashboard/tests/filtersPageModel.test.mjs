import test from "node:test";
import assert from "node:assert/strict";

const {
  buildFilterDryRunPayload,
  buildFilterDryRunPlan,
  buildFilterMutationPayload,
  buildFilterSavePlan,
  filterActionOptions,
  filterDryRunHelpText,
  filterFieldVisibility,
  filterFormActionSpecs,
  filterHeaderNavItems,
  filterKindOptions,
  filterRegexHelpItems,
  filterRegexHelpText,
  filterSensitivityOptions,
  filterSeverityOptions,
  safeFilterMutationErrorMessage,
  validateFilterFormState,
} = await import("../static/filtersPageModel.js");

const baseForm = {
  mode: "create",
  id: null,
  origin: "custom",
  kind: "keyword",
  category: "Custom",
  label: " Sensitive Terms ",
  description: "  ",
  placeholder: " SECRET ",
  severity: "medium",
  action: "MASK",
  enabled: true,
  keywords: " alpha, beta ,, ",
  exclusionKeywords: " public, approved ",
  pattern: "",
  contextGroups: "finance: budget, forecast\nstrategy: roadmap",
  windowSize: "80",
  minConditionCount: "2",
  sensitivity: "high",
};

test("filter form action specs make save a real submit and dry-run a button", () => {
  assert.deepEqual(filterFormActionSpecs(false), [
    { id: "save", label: "저장", type: "submit", disabled: false },
    { id: "dry-run", label: "미리 실행", type: "button", disabled: true },
  ]);
  assert.equal(filterFormActionSpecs(true)[1].disabled, false);
});

test("custom keyword create payload preserves documented keyword contract", () => {
  const payload = buildFilterMutationPayload(baseForm);

  assert.deepEqual(payload, {
    category: "Custom",
    label: "Sensitive Terms",
    description: null,
    placeholder: "SECRET",
    severity: "medium",
    action: "MASK",
    enabled: true,
    config_json: {
      keywords: ["alpha", "beta"],
      exclusion_keywords: ["public", "approved"],
    },
    kind: "keyword",
    keyword: "alpha",
  });
});

test("filter select options expose Korean labels while preserving API enum values", () => {
  assert.deepEqual(filterKindOptions(), [
    { value: "keyword", label: "키워드" },
    { value: "regex", label: "정규식" },
    { value: "context_rule", label: "업무 맥락" },
  ]);
  assert.deepEqual(filterSeverityOptions(), [
    { value: "low", label: "낮음" },
    { value: "medium", label: "보통" },
    { value: "high", label: "높음" },
    { value: "critical", label: "심각" },
  ]);
  assert.deepEqual(filterActionOptions(), [
    { value: "ALLOW", label: "허용" },
    { value: "WARN", label: "경고" },
    { value: "MASK", label: "마스킹" },
    { value: "BLOCK", label: "차단" },
  ]);
  assert.deepEqual(filterSensitivityOptions(), [
    { value: "low", label: "낮음" },
    { value: "medium", label: "보통" },
    { value: "high", label: "높음" },
  ]);
});

test("filter guidance makes server dry-run oracle and regex semantics explicit", () => {
  const regexHelpItems = filterRegexHelpItems();

  assert.match(filterDryRunHelpText(), /서버의 실제 필터 엔진/);
  assert.match(filterDryRunHelpText(), /샘플은 저장하지 않고/);
  assert.ok(regexHelpItems.length >= 10);
  assert.ok(regexHelpItems.every((item) => item.length <= 100));
  assert.equal(filterRegexHelpText(), regexHelpItems.join(" "));
  assert.match(regexHelpItems[0], /정규식은 글자 모양의 규칙/);
  assert.match(regexHelpItems[1], /그대로 찾을 단어는 그대로 입력/);
  assert.match(filterRegexHelpText(), /\[0-9\]는 숫자 한 글자/);
  assert.match(filterRegexHelpText(), /\+는 바로 앞 규칙이 1번 이상 반복/);
  assert.match(filterRegexHelpText(), /\[abc\]는 a, b, c 중 한 글자/);
  assert.match(filterRegexHelpText(), /\?는 바로 앞 규칙이 없어도 되고 1번 있어도 된다는 뜻/);
  assert.match(filterRegexHelpText(), /\*는 0번 이상 반복/);
  assert.match(filterRegexHelpText(), /\{3\}은 정확히 3번/);
  assert.match(filterRegexHelpText(), /\^는 문장 시작/);
  assert.match(filterRegexHelpText(), /\$는 문장 끝/);
  assert.match(filterRegexHelpText(), /\\d는 숫자/);
  assert.match(filterRegexHelpText(), /\\s는 공백/);
  assert.match(filterRegexHelpText(), /\\w는 영문자, 숫자, 밑줄/);
  assert.match(filterRegexHelpText(), /괄호\(\)는 여러 글자를 하나의 묶음/);
  assert.match(filterRegexHelpText(), /마침표, 괄호, 별표, 물음표/);
  assert.match(filterRegexHelpText(), /저장 또는 미리 실행 시 서버가 검사/);
});

test("filter field visibility follows rule kind and action semantics", () => {
  assert.deepEqual(filterFieldVisibility(baseForm), {
    canEditIdentity: true,
    showPlaceholder: true,
    showKeywordFields: true,
    showRegexFields: false,
    showContextFields: false,
  });

  assert.deepEqual(filterFieldVisibility({ ...baseForm, kind: "regex", action: "WARN" }), {
    canEditIdentity: true,
    showPlaceholder: false,
    showKeywordFields: false,
    showRegexFields: true,
    showContextFields: false,
  });

  assert.deepEqual(filterFieldVisibility({ ...baseForm, kind: "context_rule", action: "BLOCK" }), {
    canEditIdentity: true,
    showPlaceholder: false,
    showKeywordFields: false,
    showRegexFields: false,
    showContextFields: true,
  });

  assert.deepEqual(filterFieldVisibility({ ...baseForm, mode: "edit", origin: "built_in", kind: "detector" }), {
    canEditIdentity: false,
    showPlaceholder: false,
    showKeywordFields: false,
    showRegexFields: false,
    showContextFields: false,
  });
});

test("non-mask actions do not send masking placeholder", () => {
  for (const action of ["ALLOW", "WARN", "BLOCK"]) {
    const payload = buildFilterMutationPayload({ ...baseForm, action, placeholder: "SHOULD_NOT_SEND" });
    assert.equal(payload.placeholder, null);
  }
});

test("built-in update payload keeps allowed fields and drops forbidden metadata under normal mutation path", () => {
  const payload = buildFilterMutationPayload({
    ...baseForm,
    mode: "edit",
    id: "builtin-email",
    origin: "built_in",
    kind: "detector",
    category: "PII",
    label: "Admin changed label",
    placeholder: "RAW_EMAIL",
    severity: "high",
    action: "BLOCK",
    enabled: false,
    keywords: "admin@example.com",
  });

  assert.deepEqual(payload, {
    severity: "high",
    action: "BLOCK",
    enabled: false,
  });
  assert.equal(Object.hasOwn(payload, "label"), false);
  assert.equal(Object.hasOwn(payload, "config_json"), false);
  assert.equal(Object.hasOwn(payload, "placeholder"), false);
});

test("custom regex and context rule payloads keep their documented shapes", () => {
  const regexPayload = buildFilterMutationPayload({
    ...baseForm,
    kind: "regex",
    pattern: " secret-[0-9]+ ",
  });
  assert.equal(regexPayload.kind, "regex");
  assert.equal(regexPayload.pattern, "secret-[0-9]+");
  assert.deepEqual(regexPayload.config_json, {
    pattern: "secret-[0-9]+",
    exclusion_keywords: ["public", "approved"],
  });

  const contextPayload = buildFilterMutationPayload({
    ...baseForm,
    kind: "context_rule",
    windowSize: "120",
    minConditionCount: "2",
    sensitivity: "high",
  });
  assert.equal(contextPayload.kind, "context_rule");
  assert.deepEqual(contextPayload.config_json, {
    keyword_groups: {
      finance: ["budget", "forecast"],
      strategy: ["roadmap"],
    },
    exclusion_keywords: ["public", "approved"],
    window_size: 120,
    min_condition_count: 2,
    sensitivity: "high",
  });
});

test("dry-run payload is request-only and switches between existing rule and draft rule", () => {
  assert.deepEqual(
    buildFilterDryRunPayload({ ...baseForm, mode: "edit", id: "rule-1" }, "raw sample SECRET"),
    {
      sample_text: "raw sample SECRET",
      rule_id: "rule-1",
    },
  );

  const draftPayload = buildFilterDryRunPayload(baseForm, "raw sample SECRET");
  assert.equal(draftPayload.sample_text, "raw sample SECRET");
  assert.equal(Object.hasOwn(draftPayload, "draft_rule"), true);
  assert.equal(Object.hasOwn(draftPayload, "sample_persisted"), false);
});

test("filter header marks logout as dashboard-session invalidating navigation", () => {
  const logout = filterHeaderNavItems().find((item) => item.id === "logout");

  assert.deepEqual(logout, {
    id: "logout",
    label: "로그아웃",
    href: "login.html",
    className: "logout-button",
    requiresSessionLogout: true,
  });
});

test("safe filter mutation error message does not leak backend details", () => {
  const secretDetail = "Traceback DATABASE_URL=postgres://secret token=abc raw sample SECRET";

  assert.equal(safeFilterMutationErrorMessage(400, secretDetail), "입력값을 확인해 주세요.");
  assert.equal(
    safeFilterMutationErrorMessage(403, secretDetail),
    "대시보드 권한 또는 보안 토큰을 확인할 수 없습니다. 다시 로그인해 주세요.",
  );
  assert.equal(
    safeFilterMutationErrorMessage(500, secretDetail),
    "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
  );
});

test("filter form validation defines required field contract before API mutation", () => {
  assert.deepEqual(validateFilterFormState({ ...baseForm, label: " " }), [
    { field: "label", message: "규칙 이름을 입력해 주세요." },
  ]);

  assert.deepEqual(validateFilterFormState({ ...baseForm, kind: "keyword", keywords: " , " }), [
    { field: "keywords", message: "키워드를 하나 이상 입력해 주세요." },
  ]);

  assert.deepEqual(validateFilterFormState({ ...baseForm, kind: "regex", pattern: " " }), [
    { field: "pattern", message: "정규식 패턴을 입력해 주세요." },
  ]);

  assert.deepEqual(validateFilterFormState({ ...baseForm, kind: "regex", pattern: "x".repeat(1001) }), [
    { field: "pattern", message: "정규식 패턴은 1000자 이하로 입력해 주세요." },
  ]);

  assert.deepEqual(validateFilterFormState({ ...baseForm, kind: "context_rule", contextGroups: "broken line" }), [
    { field: "contextGroups", message: "업무 맥락 그룹을 '그룹명: 키워드1, 키워드2' 형식으로 입력해 주세요." },
  ]);

  assert.deepEqual(validateFilterFormState({ ...baseForm, kind: "context_rule", windowSize: "0" }), [
    { field: "windowSize", message: "검사 범위는 1 이상의 정수로 입력해 주세요." },
  ]);

  assert.deepEqual(validateFilterFormState({ ...baseForm, kind: "context_rule", minConditionCount: "1.5" }), [
    { field: "minConditionCount", message: "최소 조건 수는 1 이상의 정수로 입력해 주세요." },
  ]);
});

test("filter save plan never builds an API request for invalid form state", () => {
  assert.deepEqual(buildFilterSavePlan({ ...baseForm, label: " " }), {
    kind: "validation_error",
    errors: [{ field: "label", message: "규칙 이름을 입력해 주세요." }],
  });
});

test("filter save plan maps valid create and update states to documented API requests", () => {
  assert.deepEqual(buildFilterSavePlan(baseForm), {
    kind: "request",
    path: "/dashboard/filters",
    method: "POST",
    body: buildFilterMutationPayload(baseForm),
  });

  assert.deepEqual(buildFilterSavePlan({ ...baseForm, mode: "edit", id: "rule-1" }), {
    kind: "request",
    path: "/dashboard/filters/rule-1",
    method: "PATCH",
    body: buildFilterMutationPayload({ ...baseForm, mode: "edit", id: "rule-1" }),
  });
});

test("dry-run plan validates sample and draft rule before calling API", () => {
  assert.deepEqual(buildFilterDryRunPlan(baseForm, " "), {
    kind: "validation_error",
    errors: [{ field: "sampleText", message: "미리 실행할 샘플을 입력해 주세요." }],
  });

  assert.deepEqual(buildFilterDryRunPlan({ ...baseForm, label: " " }, "sample"), {
    kind: "validation_error",
    errors: [{ field: "label", message: "규칙 이름을 입력해 주세요." }],
  });

  const plan = buildFilterDryRunPlan(baseForm, "alpha sample");
  assert.equal(plan.kind, "request");
  assert.equal(plan.path, "/dashboard/filters/dry-run");
  assert.equal(plan.method, "POST");
  assert.deepEqual(plan.body, buildFilterDryRunPayload(baseForm, "alpha sample"));
});
