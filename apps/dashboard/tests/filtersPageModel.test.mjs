import test from "node:test";
import assert from "node:assert/strict";

const {
  buildFilterDryRunPayload,
  buildFilterMutationPayload,
  filterFieldVisibility,
  filterFormActionSpecs,
  filterHeaderNavItems,
  safeFilterMutationErrorMessage,
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
