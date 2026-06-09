import { DEFAULT_POLICY_VERSION } from "./constants";
import { createClientRequestId } from "./hashing";
import type {
  AnalyzeInput,
  AnalyzeRequest,
  ContentUnavailableReason,
  ExtensionContext,
  LimitExceededCode,
  PromptInputMethod
} from "./types";

/** Composer text byte ceiling before the input becomes metadata-only. */
export const MAX_COMPOSER_TEXT_BYTES = 262_144;
/** Converted-paste byte ceiling before the input becomes metadata-only. */
export const MAX_CONVERTED_PASTE_TEXT_BYTES = 1_048_576;
/** File text byte ceiling before the input becomes metadata-only. */
export const MAX_FILE_TEXT_SCAN_BYTES = 1_048_576;

/** Options for the composer text input item. */
export interface ComposerInputOptions {
  text: string;
  inputMethod: PromptInputMethod;
}

/** Options for the converted-paste text input item. */
export interface ConvertedPasteInputOptions {
  text: string;
}

/** Options for a scanned text-file input item. */
export interface FileTextInputOptions {
  extension: string;
  mimeType: string;
  text: string;
  sizeBytes: number;
}

/** Options for a metadata-only attachment item. */
export interface AttachmentMetadataOptions {
  extension: string;
  mimeType: string;
  sizeBytes: number;
  attachmentKind: string;
  attachmentIndex: number;
}

/** Options for an unsupported attachment item. */
export interface UnsupportedAttachmentOptions {
  extension: string;
  mimeType: string;
  sizeBytes: number;
  attachmentIndex: number;
  reason?: ContentUnavailableReason;
}

/** Creates the unified Analyze request envelope with one transient input bundle. */
export function createAnalyzeRequest(context: ExtensionContext, filterConfigRevision: string, inputs: AnalyzeInput[], clientRequestId?: string): AnalyzeRequest {
  return {
    context,
    inputs,
    filter_config_revision: filterConfigRevision || DEFAULT_POLICY_VERSION,
    client_request_id: clientRequestId ?? createClientRequestId("crq")
  };
}

/** Creates the composer text input with boundary-aware size handling. */
export function createComposerInput(options: ComposerInputOptions): AnalyzeInput {
  return createTextInput("composer", options.text, MAX_COMPOSER_TEXT_BYTES, options.inputMethod);
}

/** Creates the converted-paste text input with boundary-aware size handling. */
export function createConvertedPasteInput(options: ConvertedPasteInputOptions): AnalyzeInput {
  return createTextInput("converted_paste", options.text, MAX_CONVERTED_PASTE_TEXT_BYTES);
}

/** Creates a text-file input or its oversized metadata-only fallback. */
export function createFileTextInput(options: FileTextInputOptions): AnalyzeInput {
  if (options.sizeBytes > MAX_FILE_TEXT_SCAN_BYTES) {
    return createUnavailableTextInput("file", options.sizeBytes, "oversized", "MAX_FILE_TEXT_SCAN_BYTES");
  }
  return {
    input_id: createClientRequestId("in"),
    kind: "text",
    source: "file",
    size_bytes: options.sizeBytes,
    content_included: true,
    content: options.text,
    metadata: {
      extension: trimLeadingDot(options.extension),
      mime: options.mimeType || "text/plain"
    }
  };
}

/** Creates a metadata-only attachment input from safe attachment facts. */
export function createAttachmentMetadataInput(options: AttachmentMetadataOptions): AnalyzeInput {
  return {
    input_id: createClientRequestId("in"),
    kind: "attachment_metadata",
    source: "attachment_chip",
    size_bytes: options.sizeBytes,
    content_included: false,
    metadata: {
      extension: trimLeadingDot(options.extension),
      mime: options.mimeType,
      size_bytes: options.sizeBytes,
      attachment_kind: options.attachmentKind,
      attachment_index: options.attachmentIndex
    }
  };
}

/** Creates an unsupported-attachment input without original filename leakage. */
export function createUnsupportedAttachmentInput(options: UnsupportedAttachmentOptions): AnalyzeInput {
  return {
    input_id: createClientRequestId("in"),
    kind: "unsupported_attachment",
    source: "attachment_chip",
    size_bytes: options.sizeBytes,
    content_included: false,
    content_unavailable_reason: options.reason ?? "unsupported",
    metadata: {
      extension: trimLeadingDot(options.extension),
      mime: options.mimeType,
      size_bytes: options.sizeBytes,
      attachment_kind: attachmentKindForMime(options.mimeType),
      attachment_index: options.attachmentIndex
    }
  };
}

/** Creates a metadata-only text input for oversized or unavailable content. */
export function createUnavailableTextInput(
  source: "composer" | "converted_paste" | "file",
  sizeBytes: number,
  reason: ContentUnavailableReason,
  limitExceeded: LimitExceededCode
): AnalyzeInput {
  return {
    input_id: createClientRequestId("in"),
    kind: "text",
    source,
    size_bytes: sizeBytes,
    content_included: false,
    content_unavailable_reason: reason,
    limit_exceeded: limitExceeded
  };
}

function createTextInput(source: "composer" | "converted_paste", text: string, maxBytes: number, inputMethod?: PromptInputMethod): AnalyzeInput {
  const sizeBytes = utf8Length(text);
  if (sizeBytes > maxBytes) {
    return createUnavailableTextInput(
      source,
      sizeBytes,
      "oversized",
      source === "composer" ? "MAX_COMPOSER_TEXT_BYTES" : "MAX_CONVERTED_PASTE_TEXT_BYTES"
    );
  }
  const metadata = inputMethod ? { input_method: inputMethod } : undefined;
  return {
    input_id: createClientRequestId("in"),
    kind: "text",
    source,
    size_bytes: sizeBytes,
    content_included: true,
    content: text,
    metadata
  };
}

function attachmentKindForMime(mimeType: string): string {
  return mimeType.startsWith("image/") ? "image" : "file";
}

function trimLeadingDot(value: string): string {
  return value.replace(/^\./, "");
}

function utf8Length(value: string): number {
  return new TextEncoder().encode(value).length;
}
