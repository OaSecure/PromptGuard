import test from "node:test";
import assert from "node:assert/strict";

const {
  deriveEventDetailScreenState,
  parseEventIdFromLocationSearch,
  projectBusinessContextRows,
  projectDetectionRows,
  projectEventDetailSummary,
  projectInputRows,
  safeEventDetailErrorMessage,
} = await import("../static/eventDetailPageModel.js");

test("parseEventIdFromLocationSearch extracts and trims event_id", () => {
  assert.equal(parseEventIdFromLocationSearch("?event_id=evt-1"), "evt-1");
  assert.equal(parseEventIdFromLocationSearch("?event_id=%20evt-2%20"), "evt-2");
  assert.equal(parseEventIdFromLocationSearch("?risk=high"), null);
});

test("projectEventDetailSummary maps metadata-only summary fields", () => {
  const summary = projectEventDetailSummary({
    event_id: "evt-1",
    created_at: "2026-06-10T12:00:00Z",
    login_id: "alice",
    username: "Alice Kim",
    service: "ChatGPT",
    platform: "web",
    action: "BLOCK",
    risk_score: 95,
    risk_level: "critical",
    primary_detection_category: "PII",
    primary_detection_type: "API_KEY",
    detection_count: 2,
    input_count: 3,
    content_unavailable_count: 1,
    detail_available: true,
    detection_summary: [{ category: "PII", type: "API_KEY", count: 2 }],
    detections: [],
    input_results: [],
    content_unavailable_inputs: [],
    business_context_matches: [],
  });

  assert.equal(summary.eventId, "evt-1");
  assert.equal(summary.createdAt, "2026-06-10 12:00");
  assert.equal(summary.action, "BLOCK");
  assert.equal(summary.riskLevel, "critical");
  assert.equal(summary.inputCount, "3");
  assert.equal(summary.contentUnavailableCount, "1");
});

test("projection helpers keep metadata-only values and safe fallbacks", () => {
  const detections = projectDetectionRows([
    {
      category: "PII",
      type: "EMAIL",
      input_id: "composer-1",
      input_index: 0,
      kind: "text",
      source: "composer",
      rule_id: "rule-1",
      detector_id: "detector-1",
      severity: "high",
      action: "MASK",
      placeholder: "[EMAIL]",
      reason_code: "PII_EMAIL_DETECTED",
      match_count: 2,
    },
  ]);
  const inputs = projectInputRows([
    {
      input_id: "attachment-1",
      input_index: 1,
      kind: "unsupported_attachment",
      source: "attachment_chip",
      content_included: false,
      content_scanned: false,
      decision_basis: "content_unavailable",
      content_unavailable_reason: "unsupported_attachment",
      limit_exceeded: "attachment_scan_not_supported",
    },
  ]);
  const contexts = projectBusinessContextRows([
    {
      input_id: "composer-1",
      input_index: 0,
      kind: "text",
      source: "composer",
      category: "Business Context",
      reason_code: "BUSINESS_CONTEXT_MATCH",
      match_count: 2,
      matched_keywords: ["finance"],
      evidence_counts: { match_count: 2, matched_condition_count: 1 },
    },
  ]);

  assert.equal(detections[0].type, "EMAIL");
  assert.equal(detections[0].source, "composer");
  assert.equal(inputs[0].decisionBasis, "content_unavailable");
  assert.equal(inputs[0].contentUnavailableReason, "unsupported_attachment");
  assert.equal(contexts[0].matchedKeywords, "finance");
  assert.equal(contexts[0].evidenceCounts, "match_count: 2, matched_condition_count: 1");
});

test("deriveEventDetailScreenState returns loading, empty, ready, and error states", () => {
  assert.deepEqual(deriveEventDetailScreenState("loading", false), {
    kind: "loading",
    message: "데이터를 불러오는 중입니다.",
  });
  assert.deepEqual(deriveEventDetailScreenState("ready", false), {
    kind: "empty",
    message: "표시할 데이터가 없습니다.",
  });
  assert.deepEqual(deriveEventDetailScreenState("ready", true), {
    kind: "ready",
    message: "",
  });
  assert.deepEqual(deriveEventDetailScreenState("error", false), {
    kind: "error",
    message: "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
  });
});

test("safeEventDetailErrorMessage stays generic and fail-closed", () => {
  assert.equal(safeEventDetailErrorMessage(400), "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.");
  assert.equal(safeEventDetailErrorMessage(401), "대시보드 로그인이 필요합니다.");
  assert.equal(safeEventDetailErrorMessage(403), "대시보드 로그인이 필요합니다.");
  assert.equal(safeEventDetailErrorMessage(404), "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.");
  assert.equal(safeEventDetailErrorMessage(0), "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
});
