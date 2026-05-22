import { describe, expect, it } from "vitest";
import { DEFAULT_POLICY_VERSION } from "../../src/shared/constants";
import { isAnalyzeResponse, isFilesAnalyzeResponse } from "../../src/shared/responseValidation";
import type { AnalyzeResponse, FilesAnalyzeResponse } from "../../src/shared/types";

describe("analyze response validation", () => {
  it("accepts valid prompt and files analyze responses", () => {
    expect(isAnalyzeResponse(promptResponse("Allow"))).toBe(true);
    expect(isAnalyzeResponse(promptResponse("Mask", "[masked]"))).toBe(true);
    expect(isFilesAnalyzeResponse(filesResponse("Allow"))).toBe(true);
  });

  it("rejects malformed prompt analyze responses", () => {
    expect(isAnalyzeResponse({ ...promptResponse("Allow"), decision: { ...promptResponse("Allow").decision, action: "Review" } })).toBe(false);
    expect(isAnalyzeResponse({ ...promptResponse("Mask"), masked_prompt: undefined })).toBe(false);
    expect(isAnalyzeResponse({ ...promptResponse("Allow"), policy: { version: DEFAULT_POLICY_VERSION } })).toBe(false);
  });

  it("rejects malformed files analyze responses", () => {
    expect(isFilesAnalyzeResponse({ ...filesResponse("Allow"), file_results: [{ client_file_id: "file_test" }] })).toBe(false);
    expect(isFilesAnalyzeResponse({ ...filesResponse("Allow"), decision: { ...filesResponse("Allow").decision, risk_score: Number.NaN } })).toBe(false);
    expect(isFilesAnalyzeResponse({ ...filesResponse("Allow"), partial_result: "false" })).toBe(false);
  });
});

function promptResponse(action: AnalyzeResponse["decision"]["action"], maskedPrompt?: string): AnalyzeResponse {
  return {
    event_id: "evt_test",
    request_id: "req_test",
    decision: {
      risk_score: action === "Allow" ? 1 : 80,
      risk_level: action === "Allow" ? "LOW" : "HIGH",
      action,
      user_message: "PromptGuard decision",
      allow_original_send: action === "Allow"
    },
    detections: [],
    masked_prompt: maskedPrompt,
    policy: {
      version: DEFAULT_POLICY_VERSION,
      latest_version: DEFAULT_POLICY_VERSION
    },
    partial_result: false
  };
}

function filesResponse(action: FilesAnalyzeResponse["decision"]["action"]): FilesAnalyzeResponse {
  return {
    event_id: "evt_file_test",
    request_id: "req_file_test",
    decision: {
      risk_score: action === "Allow" ? 1 : 80,
      risk_level: action === "Allow" ? "LOW" : "HIGH",
      action,
      user_message: "PromptGuard file decision",
      allow_original_upload: action === "Allow"
    },
    file_results: [
      {
        client_file_id: "file_test",
        extension: ".txt",
        mime_type: "text/plain",
        size_bytes: 4,
        detections: []
      }
    ],
    policy: {
      version: DEFAULT_POLICY_VERSION,
      latest_version: DEFAULT_POLICY_VERSION
    },
    partial_result: false
  };
}
