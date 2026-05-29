import { describe, expect, it } from "vitest";
import { isExtensionMessage } from "../../src/shared/messageTypes";

describe("extension message guard", () => {
  it("accepts known messages with the minimum required payload shape", () => {
    expect(isExtensionMessage({ type: "GET_CONFIG_REQUEST" })).toBe(true);
    expect(isExtensionMessage({ type: "AUTH_ME_REQUEST" })).toBe(true);
    expect(isExtensionMessage({ type: "AUTH_LOGIN_REQUEST", payload: { token: "test-token" } })).toBe(true);
    expect(isExtensionMessage({ type: "AUTH_LOGIN_REQUEST", payload: { token: "test-token", refreshToken: "test-refresh-token" } })).toBe(true);
    expect(isExtensionMessage({ type: "PROMPT_ANALYZE_REQUEST", payload: promptAnalyzeRequest() })).toBe(true);
    expect(isExtensionMessage({ type: "FILES_ANALYZE_REQUEST", payload: filesAnalyzeRequest() })).toBe(true);
  });

  it("rejects unknown or malformed messages before routing", () => {
    expect(isExtensionMessage(null)).toBe(false);
    expect(isExtensionMessage({ type: "UNKNOWN_REQUEST" })).toBe(false);
    expect(isExtensionMessage({ type: "AUTH_LOGIN_REQUEST" })).toBe(false);
    expect(isExtensionMessage({ type: "AUTH_LOGIN_REQUEST", payload: { token: "" } })).toBe(false);
    expect(isExtensionMessage({ type: "AUTH_LOGIN_REQUEST", payload: { token: 123 } })).toBe(false);
    expect(isExtensionMessage({ type: "AUTH_LOGIN_REQUEST", payload: { token: "test-token", refreshToken: " " } })).toBe(false);
    expect(isExtensionMessage({ type: "PROMPT_ANALYZE_REQUEST" })).toBe(false);
    expect(isExtensionMessage({ type: "FILES_ANALYZE_REQUEST", payload: null })).toBe(false);
  });

  it("rejects malformed analyze request payloads", () => {
    expect(isExtensionMessage({ type: "PROMPT_ANALYZE_REQUEST", payload: { prompt: {}, context: {}, policy: {}, client_request_id: "crq_test" } })).toBe(false);
    expect(
      isExtensionMessage({
        type: "PROMPT_ANALYZE_REQUEST",
        payload: { ...promptAnalyzeRequest(), prompt: { text: "text", input_method: "PASTE", content_length: 4 } }
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
        payload: { ...filesAnalyzeRequest(), files: [] }
      })
    ).toBe(false);
    expect(
      isExtensionMessage({
        type: "FILES_ANALYZE_REQUEST",
        payload: { ...filesAnalyzeRequest(), files: [{ ...fileInput(), extension: "" }] }
      })
    ).toBe(false);
  });
});

function promptAnalyzeRequest() {
  return {
    prompt: { text: "text", input_method: "ENTER", content_length: 4 },
    context: context(),
    policy: { version: "v-test" },
    client_request_id: "crq_test"
  };
}

function filesAnalyzeRequest() {
  return {
    files: [fileInput()],
    context: context(),
    policy: { version: "v-test" },
    client_request_id: "frq_test"
  };
}

function fileInput() {
  return {
    client_file_id: "file_test",
    extension: ".txt",
    mime_type: "text/plain",
    size_bytes: 4,
    content_text: "text"
  };
}

function context() {
  return {
    ai_service: "CHATGPT",
    ai_service_domain: "chatgpt.com",
    page_url_origin: "https://chatgpt.com",
    extension_version: "0.4.0",
    browser: "Chrome",
    locale: "en-US"
  };
}
