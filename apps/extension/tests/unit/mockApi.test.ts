import { describe, expect, it } from "vitest";
import { DEFAULT_POLICY_VERSION } from "../../src/shared/constants";
import { createClientRequestId } from "../../src/shared/hashing";
import { mockFilesAnalyze, mockPromptAnalyze } from "../../src/background/mockApi";
import type { AnalyzeRequest, ExtensionContext, FilesAnalyzeRequest } from "../../src/shared/types";

const context: ExtensionContext = {
  ai_service: "CHATGPT",
  ai_service_domain: "chatgpt.com",
  page_url_origin: "https://chatgpt.com",
  extension_version: "0.4.0",
  browser: "Chrome",
  locale: "ko-KR"
};

describe("mock API", () => {
  it("returns Mask without allowing automatic send", async () => {
    const request: AnalyzeRequest = {
      prompt: { text: "mock:mask contact member@example.com", input_method: "ENTER", content_length: 36 },
      context,
      policy: { version: DEFAULT_POLICY_VERSION },
      client_request_id: createClientRequestId("crq")
    };

    const response = await mockPromptAnalyze(request);

    expect(response.decision.action).toBe("Mask");
    expect(response.decision.allow_original_send).toBe(false);
    expect(response.masked_prompt).toBe("[masked-trigger] contact [masked-email]");
  });

  it("does not treat a bare at-sign picker token as a mask trigger", async () => {
    const request: AnalyzeRequest = {
      prompt: { text: "@", input_method: "ENTER", content_length: 1 },
      context,
      policy: { version: DEFAULT_POLICY_VERSION },
      client_request_id: createClientRequestId("crq")
    };

    const response = await mockPromptAnalyze(request);

    expect(response.decision.action).toBe("Allow");
    expect(response.masked_prompt).toBeUndefined();
  });

  it("blocks env-like file content in mock mode", async () => {
    const request: FilesAnalyzeRequest = {
      files: [
        {
          client_file_id: "file_req_random",
          extension: ".env",
          mime_type: "text/plain",
          size_bytes: 42,
          content_text: "DATABASE_URL=postgres://example"
        }
      ],
      context,
      policy: { version: DEFAULT_POLICY_VERSION },
      client_request_id: createClientRequestId("frq")
    };

    const response = await mockFilesAnalyze(request);

    expect(response.decision.action).toBe("Block");
    expect(response.decision.allow_original_upload).toBe(false);
    expect(response.file_results[0].detections[0].type).toBe("DB_CONNECTION_STRING");
  });
});
