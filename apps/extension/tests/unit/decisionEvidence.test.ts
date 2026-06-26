import { describe, expect, it } from "vitest";

import { safeDecisionEvidence } from "../../src/content/decisionEvidence";
import type { AnalyzeDetection, AnalyzeResponse, DecisionAction } from "../../src/shared/types";

describe("safeDecisionEvidence", () => {
  it("shows detector names as user-facing Korean labels instead of raw categories", () => {
    const evidence = safeDecisionEvidence({
      ...responseFor("Block"),
      detections: [
        detectionFor({ category: "PII", type: "RRN", detector_id: "RRN", placeholder: "RRN" }),
        detectionFor({ category: "Payment", type: "CARD", detector_id: "CARD", placeholder: "CARD" })
      ]
    });

    expect(evidence).toContain("탐지: 주민등록번호");
    expect(evidence).toContain("탐지: 카드번호");
    expect(evidence.join(" ")).not.toContain("pii");
    expect(evidence.join(" ")).not.toContain("payment");
  });

  it("does not render a generic sensitive-context line when no context label is available", () => {
    const evidence = safeDecisionEvidence({
      ...responseFor("Block"),
      context_risk_evidence: {
        enabled: true,
        status: "candidate",
        candidate_count: 1,
        accepted_count: 0,
        labels: [],
        status_counts: {},
        reason_code: "RISK_CONTEXT_LR_ONLY",
        classifier_model_versions: [],
        verifier_model_versions: []
      },
      detections: [
        detectionFor({ category: "PII", type: "RRN", detector_id: "RRN", placeholder: "RRN" })
      ]
    });

    expect(evidence).toContain("탐지: 주민등록번호");
    expect(evidence.join(" ")).not.toContain("민감한 맥락");
  });

  it("summarizes multiple context labels with user-facing names", () => {
    const evidence = safeDecisionEvidence({
      ...responseFor("Warn"),
      context_risk_evidence: {
        enabled: true,
        status: "candidate",
        candidate_count: 4,
        accepted_count: 0,
        labels: [
          "CONFIDENTIAL_BUSINESS_CONTEXT",
          "FINANCIAL_IDENTIFIER_CONTEXT",
          "PERSONAL_DATA_CONTEXT",
          "INTERNAL_OPERATION_CONTEXT"
        ],
        status_counts: {},
        reason_code: "RISK_CONTEXT_LR_ONLY",
        classifier_model_versions: [],
        verifier_model_versions: []
      }
    });

    expect(evidence).toContain("주의: 기밀 비즈니스 정보, 금융 식별 정보, 개인정보 외 1개");
    expect(evidence.join(" ")).not.toContain("CONFIDENTIAL_BUSINESS_CONTEXT");
  });
});

function responseFor(action: DecisionAction): AnalyzeResponse {
  return {
    event_id: "evt_test",
    request_id: "req_test",
    action,
    checked_at: new Date(0).toISOString(),
    risk_score: action === "Allow" ? 0 : 90,
    risk_level: action === "Allow" ? "low" : "critical",
    user_message: "test",
    allow_original_send: action === "Allow",
    requires_user_confirmation: action === "Warn",
    detections: [],
    input_results: [],
    content_unavailable_inputs: [],
    business_context_matches: [],
    client_request_id: "crq_test",
    filter_config_revision: "test"
  };
}

function detectionFor(overrides: Partial<AnalyzeDetection>): AnalyzeDetection {
  return {
    input_id: "in_test",
    input_index: 0,
    kind: "file_reference",
    category: "PII",
    type: "RRN",
    source: "attached_file",
    rule_id: "rule_test",
    detector_id: "RRN",
    severity: "high",
    action: "Block",
    placeholder: "RRN",
    confidence: 100,
    reason_code: "BUILT_IN_DETECTOR_RRN",
    match_count: 1,
    ...overrides
  };
}
