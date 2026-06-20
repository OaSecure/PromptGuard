import { describe, expect, it } from "vitest";
import { buildFilesInspectionAuditEvent, buildPromptInspectionAuditEvent } from "../../src/shared/auditEvents";
import { createAnalyzeRequest, createComposerInput, createFileReferenceInput } from "../../src/shared/analyzeRequestBuilder";
import { containsForbiddenDiagnosticKey } from "../../src/shared/sanitize";
import type { AnalyzeResponse, ExtensionContext } from "../../src/shared/types";

const context: ExtensionContext = {
  ai_service: "CHATGPT",
  ai_service_domain: "chatgpt.com",
  page_url_origin: "https://chatgpt.com",
  extension_version: "0.4.0",
  browser: "Chrome",
  locale: "ko-KR"
};

describe("inspection audit events", () => {
  it("builds prompt audit metadata without raw prompt, mask, or server message text", () => {
    const request = createAnalyzeRequest(context, "cfg_prompt", [createComposerInput({ text: "SEEDED_PROMPT_SHOULD_NOT_SURVIVE", inputMethod: "CLICK" })], "crq_test");
    const response: AnalyzeResponse = {
      event_id: "evt_prompt",
      request_id: "req_prompt",
      action: "Mask",
      checked_at: "2026-06-09T00:00:00Z",
      risk_level: "high",
      risk_score: 91,
      user_message: "server echoed secret-value",
      allow_original_send: false,
      requires_user_confirmation: false,
      detections: [
        {
          input_id: request.inputs[0].input_id,
          input_index: 0,
          kind: "text",
          category: "PII",
          type: "EMAIL",
          source: "composer",
          rule_id: null,
          detector_id: "mock",
          severity: "high",
          action: "Mask",
          placeholder: "EMAIL",
          confidence: 0.9,
          reason_code: "match",
          match_count: 2
        }
      ],
      input_results: [],
      content_unavailable_inputs: [],
      business_context_matches: [],
      client_request_id: "crq_test",
      filter_config_revision: "cfg_prompt",
      masked_prompt: "SEEDED_MASKED_PROMPT_SHOULD_NOT_SURVIVE"
    };

    const event = buildPromptInspectionAuditEvent(request, response);
    const serialized = JSON.stringify(event);

    expect(event).toMatchObject({
      surface: "prompt",
      event_id: "evt_prompt",
      request_id: "req_prompt",
      client_request_id: "crq_test",
      action: "Mask",
      detection_count: 2
    });
    expect(containsForbiddenDiagnosticKey(event)).toBe(false);
    expect(serialized).not.toContain("SEEDED_PROMPT_SHOULD_NOT_SURVIVE");
    expect(serialized).not.toContain("SEEDED_MASKED_PROMPT_SHOULD_NOT_SURVIVE");
    expect(serialized).not.toContain("secret-value");
  });

  it("builds file audit metadata without file content, filenames, or raw detections", () => {
    const request = createAnalyzeRequest(context, "cfg_file", [createFileReferenceInput({ fileRef: "fref_opaque_123", fileKind: "plain_text", extension: ".txt", mimeType: "text/plain", sizeBytes: 64 })], "frq_test");
    const response: AnalyzeResponse = {
      event_id: "evt_files",
      request_id: "req_files",
      action: "Block",
      checked_at: "2026-06-09T00:00:00Z",
      risk_level: "critical",
      risk_score: 99,
      user_message: "server echoed customer-project.env",
      allow_original_send: false,
      requires_user_confirmation: false,
      detections: [
        {
          input_id: request.inputs[0].input_id,
          input_index: 0,
          kind: "file_reference",
          category: "Built-in",
          type: "DB_CONNECTION_STRING",
          source: "attached_file",
          rule_id: null,
          detector_id: "mock",
          severity: "critical",
          action: "Block",
          placeholder: "DB_CONNECTION_STRING",
          confidence: 0.95,
          reason_code: "match",
          match_count: 3
        }
      ],
      input_results: [],
      content_unavailable_inputs: [],
      business_context_matches: [],
      client_request_id: "frq_test",
      filter_config_revision: "cfg_file"
    };

    const event = buildFilesInspectionAuditEvent(request, response);
    const serialized = JSON.stringify(event);

    expect(event).toMatchObject({
      surface: "files",
      event_id: "evt_files",
      request_id: "req_files",
      client_request_id: "frq_test",
      action: "Block",
      detection_count: 3,
      file_count: 1
    });
    expect(containsForbiddenDiagnosticKey(event)).toBe(false);
    expect(serialized).not.toContain("SEEDED_FILE_SHOULD_NOT_SURVIVE");
    expect(serialized).not.toContain("customer-project.env");
  });
});
