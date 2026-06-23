import { DEFAULT_POLICY_VERSION } from "./constants";
import { createClientRequestId } from "./hashing";
import type {
  AnalyzeInput,
  AnalyzeFileKind,
  AnalyzeRequest,
  AnalyzeSizeBucket,
  ContentUnavailableReason,
  ExtensionContext,
  LimitExceededCode,
  PromptInputMethod
} from "./types";

/** Composer text byte ceiling before the input becomes metadata-only. */
export const MAX_COMPOSER_TEXT_BYTES = 262_144;
/** Converted-paste byte ceiling before the input becomes metadata-only. */
export const MAX_CONVERTED_PASTE_TEXT_BYTES = 1_048_576;

/** Options for the composer text input item. */
export interface ComposerInputOptions {
  text: string;
  inputMethod: PromptInputMethod;
}

/** Options for the converted-paste text input item. */
export interface ConvertedPasteInputOptions {
  text: string;
}

/** Options for a file-reference input item created after upload/temp. */
export interface FileReferenceInputOptions {
  fileRef: string;
  tempScopeId: string;
  fileKind: AnalyzeFileKind;
  extension: string;
  mimeType: string;
  sizeBytes: number;
  sizeBucket?: AnalyzeSizeBucket;
  source?: "pasted_file" | "pasted_image" | "screenshot_image" | "attached_file";
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

/** Creates a file-reference input from an opaque upload/temp result. */
export function createFileReferenceInput(options: FileReferenceInputOptions): AnalyzeInput {
  return {
    input_id: createClientRequestId("in"),
    kind: "file_reference",
    source: options.source ?? "attached_file",
    size_bytes: options.sizeBytes,
    content_included: false,
    file_ref: options.fileRef,
    temp_scope_id: options.tempScopeId,
    file_kind: options.fileKind,
    mime: options.mimeType,
    extension: trimLeadingDot(options.extension),
    size_bucket: options.sizeBucket ?? sizeBucketForBytes(options.sizeBytes)
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
  source: "composer" | "converted_paste",
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

function sizeBucketForBytes(sizeBytes: number): AnalyzeSizeBucket {
  if (sizeBytes <= 0) {
    return "empty";
  }
  if (sizeBytes <= 1_048_576) {
    return "small";
  }
  if (sizeBytes <= 10_485_760) {
    return "medium";
  }
  return "large";
}
