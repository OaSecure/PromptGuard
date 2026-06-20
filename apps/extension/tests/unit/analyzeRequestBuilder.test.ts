import { describe, expect, it } from "vitest";
import {
  MAX_COMPOSER_TEXT_BYTES,
  MAX_CONVERTED_PASTE_TEXT_BYTES,
  createAnalyzeRequest,
  createAttachmentMetadataInput,
  createComposerInput,
  createConvertedPasteInput,
  createFileReferenceInput,
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
  it("builds one unified request envelope with composer, converted paste, file reference, and attachment metadata", () => {
    const request = createAnalyzeRequest(context, "cfg_2026_06_09", [
      createComposerInput({ text: "최종 composer", inputMethod: "ENTER" }),
      createConvertedPasteInput({ text: "붙여넣기 원문" }),
      createFileReferenceInput({ fileRef: "fref_opaque_123", fileKind: "plain_text", extension: ".txt", mimeType: "text/plain", sizeBytes: 12 }),
      createAttachmentMetadataInput({ extension: ".png", mimeType: "image/png", sizeBytes: 2048, attachmentKind: "image", attachmentIndex: 0 })
    ]);

    expect(request.context).toEqual(context);
    expect(request.filter_config_revision).toBe("cfg_2026_06_09");
    expect(request.client_request_id).toMatch(/^crq_/);
    expect(request.inputs.map((item) => item.source)).toEqual(["composer", "converted_paste", "attached_file", "attachment_chip"]);
    expect(request.inputs[2]).toMatchObject({
      kind: "file_reference",
      content_included: false,
      file_ref: "fref_opaque_123",
      file_kind: "plain_text",
      extension: "txt",
      mime: "text/plain"
    });
    expect(JSON.stringify(request)).not.toContain("file content");
    expect(JSON.stringify(request)).not.toContain("\"prompt\"");
    expect(JSON.stringify(request)).not.toContain("\"attachments\"");
    expect("login_id" in (request as unknown as Record<string, unknown>)).toBe(false);
  });

  it("marks oversized composer and converted paste as content unavailable", () => {
    const composer = createComposerInput({ text: "a".repeat(MAX_COMPOSER_TEXT_BYTES + 1), inputMethod: "CLICK" });
    const converted = createConvertedPasteInput({ text: "b".repeat(MAX_CONVERTED_PASTE_TEXT_BYTES + 1) });

    expect(composer).toMatchObject({ source: "composer", content_included: false, content_unavailable_reason: "oversized", limit_exceeded: "MAX_COMPOSER_TEXT_BYTES" });
    expect(converted).toMatchObject({ source: "converted_paste", content_included: false, content_unavailable_reason: "oversized", limit_exceeded: "MAX_CONVERTED_PASTE_TEXT_BYTES" });
  });

  it("keeps exact text byte limits inclusive and excludes content only after the limit", () => {
    const exactComposer = createComposerInput({ text: "a".repeat(MAX_COMPOSER_TEXT_BYTES), inputMethod: "ENTER" });
    const oversizedComposer = createComposerInput({ text: "a".repeat(MAX_COMPOSER_TEXT_BYTES + 1), inputMethod: "ENTER" });
    const exactConverted = createConvertedPasteInput({ text: "b".repeat(MAX_CONVERTED_PASTE_TEXT_BYTES) });
    const oversizedConverted = createConvertedPasteInput({ text: "b".repeat(MAX_CONVERTED_PASTE_TEXT_BYTES + 1) });

    expect(exactComposer).toMatchObject({ content_included: true, size_bytes: MAX_COMPOSER_TEXT_BYTES });
    expect(oversizedComposer).toMatchObject({ content_included: false, size_bytes: MAX_COMPOSER_TEXT_BYTES + 1 });
    expect(exactConverted).toMatchObject({ content_included: true, size_bytes: MAX_CONVERTED_PASTE_TEXT_BYTES });
    expect(oversizedConverted).toMatchObject({ content_included: false, size_bytes: MAX_CONVERTED_PASTE_TEXT_BYTES + 1 });
  });

  it("assigns file reference size buckets at contract boundaries without content", () => {
    const samples = [
      [0, "empty"],
      [1, "small"],
      [1_048_576, "small"],
      [1_048_577, "medium"],
      [10_485_760, "medium"],
      [10_485_761, "large"]
    ] as const;

    for (const [sizeBytes, sizeBucket] of samples) {
      const input = createFileReferenceInput({
        fileRef: `fref_${sizeBytes}`,
        fileKind: "plain_text",
        extension: ".txt",
        mimeType: "text/plain",
        sizeBytes
      });

      expect(input).toMatchObject({
        kind: "file_reference",
        source: "attached_file",
        content_included: false,
        extension: "txt",
        size_bucket: sizeBucket
      });
      expect("content" in input).toBe(false);
    }
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
