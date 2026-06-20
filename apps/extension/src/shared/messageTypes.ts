import type { ExtensionMessage } from "./types";

/**
 * Validates messages before the background router acts on them.
 *
 * Runtime messages cross the content/background trust boundary, so malformed
 * payloads must be rejected before they can trigger Analyze calls, storage
 * writes, or DOM replay decisions.
 */
export function isExtensionMessage(value: unknown): value is ExtensionMessage {
  if (!isRecord(value) || typeof value.type !== "string") {
    return false;
  }

  switch (value.type) {
    case "PROMPT_ANALYZE_REQUEST":
      return isAnalyzeRequest(value.payload);
    case "PROMPT_ANALYZE_RESULT":
      return isRecord(value.payload);
    case "FILES_ANALYZE_REQUEST":
      return isAnalyzeRequest(value.payload);
    case "FILES_ANALYZE_RESULT":
    case "CONFIG_SYNC_RESULT":
    case "GET_CONFIG_RESULT":
      return isRecord(value.payload);
    case "AUTH_LOGIN_REQUEST":
      return isRecord(value.payload) && isNonEmptyString(value.payload.login_id) && isNonEmptyString(value.payload.password);
    case "AUTH_ME_REQUEST":
    case "AUTH_LOGOUT_REQUEST":
    case "CONFIG_SYNC_REQUEST":
    case "GET_CONFIG_REQUEST":
      return true;
    default:
      return false;
  }
}

function isAnalyzeRequest(value: unknown): boolean {
  return (
    isRecord(value) &&
    isExtensionContext(value.context) &&
    Array.isArray(value.inputs) &&
    value.inputs.length > 0 &&
    value.inputs.every(isAnalyzeInput) &&
    isNonEmptyString(value.filter_config_revision) &&
    isNonEmptyString(value.client_request_id)
  );
}

function isAnalyzeInput(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }
  if (!isNonEmptyString(value.input_id) || !isAnalyzeInputKind(value.kind) || !isAnalyzeInputSource(value.source) || !isNonNegativeFiniteNumber(value.size_bytes)) {
    return false;
  }
  if (typeof value.content_included !== "boolean") {
    return false;
  }
  if (value.kind === "text" && value.source !== "composer" && value.source !== "converted_paste") {
    return false;
  }
  if (value.kind === "file_reference") {
    return (
      value.content_included === false &&
      value.content === undefined &&
      isNonEmptyString(value.file_ref) &&
      isNonEmptyString(value.file_kind) &&
      (value.metadata === undefined || isRecord(value.metadata)) &&
      (value.content_unavailable_reason === undefined || isNonEmptyString(value.content_unavailable_reason)) &&
      (value.limit_exceeded === undefined || isNonEmptyString(value.limit_exceeded))
    );
  }
  if (value.content_included) {
    return typeof value.content === "string";
  }
  return (
    value.content === undefined &&
    (value.metadata === undefined || isRecord(value.metadata)) &&
    (value.content_unavailable_reason === undefined || isNonEmptyString(value.content_unavailable_reason)) &&
    (value.limit_exceeded === undefined || isNonEmptyString(value.limit_exceeded))
  );
}

function isExtensionContext(value: unknown): boolean {
  return (
    isRecord(value) &&
    value.ai_service === "CHATGPT" &&
    isNonEmptyString(value.ai_service_domain) &&
    isNonEmptyString(value.page_url_origin) &&
    isNonEmptyString(value.extension_version) &&
    value.browser === "Chrome" &&
    isNonEmptyString(value.locale)
  );
}

function isAnalyzeInputKind(value: unknown): boolean {
  return value === "text" || value === "file_reference" || value === "attachment_metadata" || value === "unsupported_attachment";
}

function isAnalyzeInputSource(value: unknown): boolean {
  return value === "composer" || value === "converted_paste" || value === "pasted_file" || value === "pasted_image" || value === "screenshot_image" || value === "attached_file" || value === "attachment_chip";
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isNonNegativeFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
