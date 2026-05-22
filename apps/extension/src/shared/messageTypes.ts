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
      return isFilesAnalyzeRequest(value.payload);
    case "FILES_ANALYZE_RESULT":
    case "CONFIG_SYNC_RESULT":
    case "GET_CONFIG_RESULT":
      return isRecord(value.payload);
    case "AUTH_LOGIN_REQUEST":
      return isRecord(value.payload) && isNonEmptyString(value.payload.token);
    case "AUTH_ME_REQUEST":
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
    isRecord(value.prompt) &&
    typeof value.prompt.text === "string" &&
    isPromptInputMethod(value.prompt.input_method) &&
    isNonNegativeFiniteNumber(value.prompt.content_length) &&
    isExtensionContext(value.context) &&
    isPolicyRef(value.policy) &&
    isNonEmptyString(value.client_request_id)
  );
}

function isFilesAnalyzeRequest(value: unknown): boolean {
  return (
    isRecord(value) &&
    Array.isArray(value.files) &&
    value.files.length > 0 &&
    value.files.every(isFileAnalyzeInput) &&
    isExtensionContext(value.context) &&
    isPolicyRef(value.policy) &&
    isNonEmptyString(value.client_request_id)
  );
}

function isFileAnalyzeInput(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonEmptyString(value.client_file_id) &&
    (value.name_hash === undefined || typeof value.name_hash === "string") &&
    isNonEmptyString(value.extension) &&
    typeof value.mime_type === "string" &&
    isNonNegativeFiniteNumber(value.size_bytes) &&
    typeof value.content_text === "string"
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

function isPolicyRef(value: unknown): boolean {
  return isRecord(value) && isNonEmptyString(value.version);
}

function isPromptInputMethod(value: unknown): boolean {
  return value === "CLICK" || value === "ENTER" || value === "UNKNOWN";
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
