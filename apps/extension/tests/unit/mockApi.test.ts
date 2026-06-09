import { describe, expect, it } from "vitest";
import { DEFAULT_POLICY_VERSION } from "../../src/shared/constants";
import { createAnalyzeRequest, createComposerInput, createFileTextInput, createUnsupportedAttachmentInput } from "../../src/shared/analyzeRequestBuilder";
import { mockFilesAnalyze, mockPromptAnalyze } from "../../src/background/mockApi";
import type { ExtensionContext } from "../../src/shared/types";

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
    const request = createAnalyzeRequest(context, DEFAULT_POLICY_VERSION, [createComposerInput({ text: "mock:mask contact member@example.com", inputMethod: "ENTER" })], "crq_test");

    const response = await mockPromptAnalyze(request);

    expect(response.action).toBe("Mask");
    expect(response.allow_original_send).toBe(false);
    expect(response.masked_prompt).toBe("[masked-trigger] contact [masked-email]");
  });

  it("does not treat a bare at-sign picker token as a mask trigger", async () => {
    const request = createAnalyzeRequest(context, DEFAULT_POLICY_VERSION, [createComposerInput({ text: "@", inputMethod: "ENTER" })], "crq_test");

    const response = await mockPromptAnalyze(request);

    expect(response.action).toBe("Allow");
    expect(response.masked_prompt).toBeUndefined();
  });

  it("warns for unsupported attachments and blocks env-like file content in mock mode", async () => {
    const warnRequest = createAnalyzeRequest(context, DEFAULT_POLICY_VERSION, [createUnsupportedAttachmentInput({ extension: ".pdf", mimeType: "application/pdf", sizeBytes: 12, attachmentIndex: 0 })], "frq_warn");
    const blockRequest = createAnalyzeRequest(context, DEFAULT_POLICY_VERSION, [createFileTextInput({ extension: ".env", mimeType: "text/plain", sizeBytes: 42, text: "DATABASE_URL=postgres://example" })], "frq_block");

    const warnResponse = await mockFilesAnalyze(warnRequest);
    const blockResponse = await mockFilesAnalyze(blockRequest);

    expect(warnResponse.action).toBe("Warn");
    expect(warnResponse.requires_user_confirmation).toBe(true);
    expect(blockResponse.action).toBe("Block");
    expect(blockResponse.allow_original_send).toBe(false);
    expect(blockResponse.detections[0].type).toBe("DB_CONNECTION_STRING");
  });
});
