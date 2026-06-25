import { describe, expect, it } from "vitest";
import { isAnalyzeResponse } from "../../src/shared/responseValidation";
import type { AnalyzeResponse } from "../../src/shared/types";

describe("analyze response validation", () => {
  it("accepts valid unified analyze responses", () => {
    expect(isAnalyzeResponse(promptResponse("Allow"))).toBe(true);
    expect(isAnalyzeResponse(promptResponse("Mask", "[masked]"))).toBe(true);
    expect(
      isAnalyzeResponse({
        ...promptResponse("Warn"),
        input_results: [{ ...promptResponse("Warn").input_results[0], decision_basis: "context_risk" }],
        context_risk_evidence: {
          enabled: true,
          status: "verified",
          candidate_count: 1,
          accepted_count: 1,
          labels: ["INTERNAL_OPERATION_CONTEXT"],
          status_counts: { confirmed: 1 },
          highest_score_bucket: "very_high",
          highest_confidence_bucket: "high",
          failure_code: null,
          reason_code: "RISK_CONTEXT_VERIFIER_CONFIRMED",
          classifier_model_versions: [],
          verifier_model_versions: ["fake-roberta-v1"]
        }
      })
    ).toBe(true);
  });

  it("rejects malformed prompt analyze responses", () => {
    expect(isAnalyzeResponse({ ...promptResponse("Allow"), action: "Review" })).toBe(false);
    expect(isAnalyzeResponse({ ...promptResponse("Mask"), masked_prompt: undefined })).toBe(false);
    expect(isAnalyzeResponse({ ...promptResponse("Allow"), input_results: [{ input_id: "in_1" }] })).toBe(false);
    expect(isAnalyzeResponse({ ...promptResponse("Allow"), risk_score: Number.NaN })).toBe(false);
    expect(isAnalyzeResponse({ ...promptResponse("Allow"), requires_user_confirmation: "false" })).toBe(false);
    expect(isAnalyzeResponse({ ...promptResponse("Allow"), input_results: [{ ...promptResponse("Allow").input_results[0], decision_basis: "no_match" }] })).toBe(false);
    expect(isAnalyzeResponse({ ...promptResponse("Allow"), context_risk_evidence: { status: "verified" } })).toBe(false);
  });
});

function promptResponse(action: AnalyzeResponse["action"], maskedPrompt?: string): AnalyzeResponse {
  return {
    event_id: "evt_test",
    request_id: "req_test",
    action,
    checked_at: "2026-06-09T00:00:00Z",
    risk_score: action === "Allow" ? 1 : 80,
    risk_level: action === "Allow" ? "low" : "high",
    user_message: "PromptGuard decision",
    allow_original_send: action === "Allow",
    requires_user_confirmation: action === "Warn",
    detections: [],
    input_results: [
      {
        input_id: "in_1",
        input_index: 0,
        kind: "text",
        source: "composer",
        content_included: true,
        content_scanned: true,
        decision_basis: action === "Allow" ? "no_detection" : "detection"
      }
    ],
    content_unavailable_inputs: [],
    business_context_matches: [],
    client_request_id: "crq_test",
    filter_config_revision: "cfg_2026_06_09",
    masked_prompt: maskedPrompt
  };
}
