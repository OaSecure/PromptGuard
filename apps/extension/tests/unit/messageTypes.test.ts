import { describe, expect, it } from "vitest";
import { isExtensionMessage } from "../../src/shared/messageTypes";
import { createAnalyzeRequest, createAttachmentMetadataInput, createComposerInput, createFileReferenceInput } from "../../src/shared/analyzeRequestBuilder";
import type { ExtensionContext } from "../../src/shared/types";

describe("extension message guard", () => {
  it("accepts known messages with the minimum required payload shape", () => {
    expect(isExtensionMessage({ type: "GET_CONFIG_REQUEST" })).toBe(true);
    expect(isExtensionMessage({ type: "AUTH_ME_REQUEST" })).toBe(true);
    expect(isExtensionMessage({ type: "AUTH_LOGOUT_REQUEST" })).toBe(true);
    expect(isExtensionMessage({ type: "AUTH_LOGIN_REQUEST", payload: { login_id: "member@example.com", password: "test-password" } })).toBe(true);
    expect(isExtensionMessage({ type: "PROMPT_ANALYZE_REQUEST", payload: promptAnalyzeRequest() })).toBe(true);
    expect(isExtensionMessage({ type: "FILES_ANALYZE_REQUEST", payload: filesAnalyzeRequest() })).toBe(true);
  });

  it("rejects unknown or malformed messages before routing", () => {
    expect(isExtensionMessage(null)).toBe(false);
    expect(isExtensionMessage({ type: "UNKNOWN_REQUEST" })).toBe(false);
    expect(isExtensionMessage({ type: "AUTH_LOGIN_REQUEST" })).toBe(false);
    expect(isExtensionMessage({ type: "AUTH_LOGIN_REQUEST", payload: { login_id: "", password: "test-password" } })).toBe(false);
    expect(isExtensionMessage({ type: "AUTH_LOGIN_REQUEST", payload: { login_id: "member@example.com", password: " " } })).toBe(false);
    expect(isExtensionMessage({ type: "AUTH_LOGIN_REQUEST", payload: { login_id: 123, password: "test-password" } })).toBe(false);
    expect(isExtensionMessage({ type: "PROMPT_ANALYZE_REQUEST" })).toBe(false);
    expect(isExtensionMessage({ type: "FILES_ANALYZE_REQUEST", payload: null })).toBe(false);
  });

  it("rejects malformed analyze request payloads", () => {
    expect(isExtensionMessage({ type: "PROMPT_ANALYZE_REQUEST", payload: { inputs: [], context: {}, client_request_id: "crq_test" } })).toBe(false);
    expect(
      isExtensionMessage({
        type: "PROMPT_ANALYZE_REQUEST",
        payload: { ...promptAnalyzeRequest(), filter_config_revision: "" }
      })
    ).toBe(false);
    expect(
      isExtensionMessage({
        type: "PROMPT_ANALYZE_REQUEST",
        payload: { ...promptAnalyzeRequest(), context: { ...context(), page_url_origin: "" } }
      })
    ).toBe(false);
    expect(
      isExtensionMessage({
        type: "FILES_ANALYZE_REQUEST",
        payload: { ...filesAnalyzeRequest(), inputs: [] }
      })
    ).toBe(false);
    expect(
      isExtensionMessage({
        type: "FILES_ANALYZE_REQUEST",
        payload: { ...filesAnalyzeRequest(), inputs: [{ ...fileInput(), source: "invalid" }] }
      })
    ).toBe(false);
  });
});

function promptAnalyzeRequest() {
  return createAnalyzeRequest(context(), "cfg_2026_06_09", [createComposerInput({ text: "text", inputMethod: "ENTER" })], "crq_test");
}

function filesAnalyzeRequest() {
  return createAnalyzeRequest(
    context(),
    "cfg_2026_06_09",
    [createFileReferenceInput({ fileRef: "fref_opaque_123", fileKind: "plain_text", extension: ".txt", mimeType: "text/plain", sizeBytes: 4 }), createAttachmentMetadataInput({ extension: ".png", mimeType: "image/png", sizeBytes: 4, attachmentKind: "image", attachmentIndex: 1 })],
    "frq_test"
  );
}

function fileInput() {
  return {
    input_id: "in_test",
    kind: "file_reference",
    source: "attached_file",
    size_bytes: 4,
    content_included: false,
    file_ref: "fref_opaque_123",
    file_kind: "plain_text"
  };
}

function context(): ExtensionContext {
  return {
    ai_service: "CHATGPT",
    ai_service_domain: "chatgpt.com",
    page_url_origin: "https://chatgpt.com",
    extension_version: "0.4.0",
    browser: "Chrome",
    locale: "en-US"
  };
}
