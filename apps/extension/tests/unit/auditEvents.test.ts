import { describe, expect, it } from "vitest";
import { buildFilesInspectionAuditEvent, buildPromptInspectionAuditEvent } from "../../src/shared/auditEvents";
import { containsForbiddenDiagnosticKey } from "../../src/shared/sanitize";
import type { AnalyzeRequest, AnalyzeResponse, FilesAnalyzeRequest, FilesAnalyzeResponse } from "../../src/shared/types";

const context = {
  ai_service: "CHATGPT" as const,
  ai_service_domain: "chatgpt.com",
  page_url_origin: "https://chatgpt.com",
  extension_version: "0.4.0",
  browser: "Chrome" as const,
  locale: "ko-KR"
};

describe("inspection audit events", () => {
  it("builds prompt audit metadata without raw prompt, mask, or server message text", () => {
    const request: AnalyzeRequest = {
      prompt: {
        text: "SEEDED_PROMPT_SHOULD_NOT_SURVIVE",
        input_method: "CLICK",
        content_length: 32
      },
      context,
      policy: { version: "policy-a" },
      client_request_id: "crq_test"
    };
    const response: AnalyzeResponse = {
      event_id: "evt_prompt",
      request_id: "req_prompt",
      decision: {
        action: "Mask",
        risk_level: "HIGH",
        risk_score: 91,
        user_message: "server echoed secret-value",
        allow_original_send: false
      },
      detections: [{ type: "secret", label: "API key", count: 2, severity: "high", confidence: 0.9, source: "prompt" }],
      masked_prompt: "SEEDED_MASKED_PROMPT_SHOULD_NOT_SURVIVE",
      policy: { version: "policy-a", latest_version: "policy-b" },
      partial_result: false
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
    const request: FilesAnalyzeRequest = {
      files: [
        {
          client_file_id: "file_a",
          extension: ".txt",
          mime_type: "text/plain",
          size_bytes: 64,
          content_text: "SEEDED_FILE_SHOULD_NOT_SURVIVE"
        }
      ],
      context,
      policy: { version: "policy-a" },
      client_request_id: "frq_test"
    };
    const response: FilesAnalyzeResponse = {
      event_id: "evt_files",
      request_id: "req_files",
      decision: {
        action: "Block",
        risk_level: "CRITICAL",
        risk_score: 99,
        user_message: "server echoed customer-project.env"
      },
      file_results: [
        {
          client_file_id: "file_a",
          extension: ".txt",
          mime_type: "text/plain",
          size_bytes: 64,
          detections: [{ type: "secret", label: "API key", count: 3, severity: "critical", confidence: 0.95, source: "file" }]
        }
      ],
      policy: { version: "policy-a", latest_version: "policy-b" },
      partial_result: true
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
    expect(serialized).not.toContain("file_a");
  });
});
