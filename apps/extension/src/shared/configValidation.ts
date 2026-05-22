import type { ExtensionConfigResponse } from "./types";

export function isExtensionConfigResponse(value: unknown): value is ExtensionConfigResponse {
  if (!isRecord(value)) {
    return false;
  }

  return (
    isNonEmptyString(value.api_base_url) &&
    isNonEmptyString(value.policy_version) &&
    isPositiveFiniteNumber(value.timeout_ms) &&
    isNonEmptyArray(value.ai_service_configs) &&
    value.ai_service_configs.every(isAiServiceConfig) &&
    isFileUploadPolicy(value.file_upload)
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
    isNonEmptyStringArray(value.selectors.drop_zone)
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
