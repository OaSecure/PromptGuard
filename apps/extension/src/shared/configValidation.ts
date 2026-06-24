import type { ExtensionConfigResponse } from "./types";

/**
 * Validates extension config before cache, render, or hook installation.
 *
 * Config controls selectors, timeout, API URL, and file policy. Rejecting
 * malformed values prevents stale storage or bad server data from disabling
 * preflight behavior.
 */
export function isExtensionConfigResponse(value: unknown): value is ExtensionConfigResponse {
  if (!isRecord(value)) {
    return false;
  }

  return (
    isNonEmptyString(value.api_base_url) &&
    isNonEmptyString(value.filter_config_revision) &&
    isRequestTimeouts(value.request_timeouts) &&
    isInputLimits(value.input_limits) &&
    isFileUploadPolicy(value.attachment_policy) &&
    isNonEmptyString(value.policy_version) &&
    isPositiveFiniteNumber(value.timeout_ms) &&
    isNonEmptyArray(value.ai_service_configs) &&
    value.ai_service_configs.every(isAiServiceConfig) &&
    isFileUploadPolicy(value.file_upload)
  );
}

function isRequestTimeouts(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }
  return isPositiveFiniteNumber(value.config_request_ms) && isPositiveFiniteNumber(value.analyze_request_ms);
}

function isInputLimits(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }
  return (
    isPositiveFiniteNumber(value.composer_text_bytes) &&
    isPositiveFiniteNumber(value.converted_paste_text_bytes) &&
    isPositiveFiniteNumber(value.file_text_scan_bytes) &&
    isPositiveFiniteNumber(value.analyze_request_bytes)
  );
}

function isAiServiceConfig(value: unknown): boolean {
  if (!isRecord(value) || !isRecord(value.selectors)) {
    return false;
  }
  return (
    value.service === "CHATGPT" &&
    isNonEmptyStringArray(value.domains) &&
    isNonEmptyStringArray(value.selectors.input) &&
    isNonEmptyStringArray(value.selectors.send_button) &&
    isNonEmptyStringArray(value.selectors.file_input) &&
    isNonEmptyStringArray(value.selectors.drop_zone) &&
    isNonEmptyStringArray(value.selectors.attachment_chip)
  );
}

function isFileUploadPolicy(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.enabled === "boolean" &&
    isPositiveFiniteNumber(value.max_file_size_bytes) &&
    isPositiveFiniteNumber(value.max_total_size_bytes) &&
    isPositiveFiniteNumber(value.max_file_count) &&
    isNonEmptyStringArray(value.allowed_extensions) &&
    isStringArray(value.excluded_extensions)
  );
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isNonEmptyStringArray(value: unknown): value is string[] {
  return isNonEmptyArray(value) && value.every(isNonEmptyString);
}

function isNonEmptyArray(value: unknown): value is unknown[] {
  return Array.isArray(value) && value.length > 0;
}

function isPositiveFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
