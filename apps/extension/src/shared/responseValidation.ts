import type { AnalyzeResponse, Decision, FilesAnalyzeResponse } from "./types";

/**
 * Validates a prompt Analyze response before controller action handling.
 *
 * A response that does not match this contract cannot authorize send replay,
 * mask replacement, or block/warn UI decisions.
 */
export function isAnalyzeResponse(value: unknown): value is AnalyzeResponse {
  return (
    isRecord(value) &&
    isNonEmptyString(value.event_id) &&
    isNonEmptyString(value.request_id) &&
    isDecision(value.decision) &&
    (value.decision.action !== "Mask" || typeof value.masked_prompt === "string") &&
    Array.isArray(value.detections) &&
    isPolicyStatus(value.policy) &&
    typeof value.partial_result === "boolean"
  );
}

/**
 * Validates a files Analyze response before upload action handling.
 *
 * Invalid file responses fail closed so native upload replay happens only after
 * a well-formed decision.
 */
export function isFilesAnalyzeResponse(value: unknown): value is FilesAnalyzeResponse {
  return (
    isRecord(value) &&
    isNonEmptyString(value.event_id) &&
    isNonEmptyString(value.request_id) &&
    isDecision(value.decision) &&
    Array.isArray(value.file_results) &&
    value.file_results.every(isFileAnalyzeResult) &&
    isPolicyStatus(value.policy) &&
    typeof value.partial_result === "boolean"
  );
}

function isDecision(value: unknown): value is Decision {
  return (
    isRecord(value) &&
    isNonNegativeFiniteNumber(value.risk_score) &&
    isRiskLevel(value.risk_level) &&
    isDecisionAction(value.action) &&
    typeof value.user_message === "string" &&
    (value.allow_original_send === undefined || typeof value.allow_original_send === "boolean") &&
    (value.allow_original_upload === undefined || typeof value.allow_original_upload === "boolean")
  );
}

function isFileAnalyzeResult(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonEmptyString(value.client_file_id) &&
    isNonEmptyString(value.extension) &&
    typeof value.mime_type === "string" &&
    isNonNegativeFiniteNumber(value.size_bytes) &&
    Array.isArray(value.detections)
  );
}

function isPolicyStatus(value: unknown): boolean {
  return isRecord(value) && isNonEmptyString(value.version) && isNonEmptyString(value.latest_version);
}

function isDecisionAction(value: unknown): boolean {
  return value === "Allow" || value === "Warn" || value === "Mask" || value === "Block";
}

function isRiskLevel(value: unknown): boolean {
  return value === "LOW" || value === "MEDIUM" || value === "HIGH" || value === "CRITICAL";
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
