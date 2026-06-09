import { describe, expect, it } from "vitest";
import {
  MAX_COMPOSER_TEXT_BYTES,
  MAX_CONVERTED_PASTE_TEXT_BYTES,
  MAX_FILE_TEXT_SCAN_BYTES,
  createAnalyzeRequest,
  createAttachmentMetadataInput,
  createComposerInput,
  createConvertedPasteInput,
  createFileTextInput,
  createUnsupportedAttachmentInput
} from "../../src/shared/analyzeRequestBuilder";
import type { ExtensionContext } from "../../src/shared/types";

const context: ExtensionContext = {
  ai_service: "CHATGPT",
  ai_service_domain: "chatgpt.com",
  page_url_origin: "https://chatgpt.com",
  extension_version: "0.4.0",
  browser: "Chrome",
  locale: "ko-KR"
};

describe("analyze request builder", () => {
  it("builds one unified request envelope with composer, converted paste, file text, and attachment metadata", () => {
    const request = createAnalyzeRequest(context, "cfg_2026_06_09", [
      createComposerInput({ text: "최종 composer", inputMethod: "ENTER" }),
      createConvertedPasteInput({ text: "붙여넣기 원문" }),
      createFileTextInput({ extension: ".txt", mimeType: "text/plain", sizeBytes: 12, text: "file content" }),
      createAttachmentMetadataInput({ extension: ".png", mimeType: "image/png", sizeBytes: 2048, attachmentKind: "image", attachmentIndex: 0 })
    ]);

    expect(request.context).toEqual(context);
    expect(request.filter_config_revision).toBe("cfg_2026_06_09");
    expect(request.client_request_id).toMatch(/^crq_/);
    expect(request.inputs.map((item) => item.source)).toEqual(["composer", "converted_paste", "file", "attachment_chip"]);
    expect(JSON.stringify(request)).not.toContain("\"prompt\"");
    expect(JSON.stringify(request)).not.toContain("\"attachments\"");
    expect("login_id" in (request as unknown as Record<string, unknown>)).toBe(false);
  });

  it("marks oversized composer, converted paste, and file text as content unavailable", () => {
    const composer = createComposerInput({ text: "a".repeat(MAX_COMPOSER_TEXT_BYTES + 1), inputMethod: "CLICK" });
    const converted = createConvertedPasteInput({ text: "b".repeat(MAX_CONVERTED_PASTE_TEXT_BYTES + 1) });
    const file = createFileTextInput({
      extension: ".txt",
      mimeType: "text/plain",
      sizeBytes: MAX_FILE_TEXT_SCAN_BYTES + 1,
      text: "c"
    });

    expect(composer).toMatchObject({ source: "composer", content_included: false, content_unavailable_reason: "oversized", limit_exceeded: "MAX_COMPOSER_TEXT_BYTES" });
    expect(converted).toMatchObject({ source: "converted_paste", content_included: false, content_unavailable_reason: "oversized", limit_exceeded: "MAX_CONVERTED_PASTE_TEXT_BYTES" });
    expect(file).toMatchObject({ source: "file", content_included: false, content_unavailable_reason: "oversized", limit_exceeded: "MAX_FILE_TEXT_SCAN_BYTES" });
  });

  it("builds unsupported attachments without original filename leakage", () => {
    const input = createUnsupportedAttachmentInput({
      extension: ".pdf",
      mimeType: "application/pdf",
      sizeBytes: 300000,
      attachmentIndex: 2
    });

    const serialized = JSON.stringify(input);
    expect(input).toMatchObject({
      kind: "unsupported_attachment",
      source: "attachment_chip",
      content_included: false,
      content_unavailable_reason: "unsupported"
    });
    expect(serialized).not.toContain("report.pdf");
    expect(serialized).not.toContain("original_filename");
  });

  it("mints a new client_request_id per send attempt", () => {
    const first = createAnalyzeRequest(context, "cfg_2026_06_09", [createComposerInput({ text: "hello", inputMethod: "ENTER" })]);
    const second = createAnalyzeRequest(context, "cfg_2026_06_09", [createComposerInput({ text: "hello", inputMethod: "ENTER" })]);

    expect(first.client_request_id).not.toBe(second.client_request_id);
  });
});
