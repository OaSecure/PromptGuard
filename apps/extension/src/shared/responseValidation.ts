import type { AnalyzeResponse } from "./types";

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
    isDecisionAction(value.action) &&
    isNonEmptyString(value.checked_at) &&
    isNonNegativeFiniteNumber(value.risk_score) &&
    isRiskLevel(value.risk_level) &&
    typeof value.user_message === "string" &&
    typeof value.allow_original_send === "boolean" &&
    typeof value.requires_user_confirmation === "boolean" &&
    (value.action !== "Mask" || typeof value.masked_prompt === "string") &&
    Array.isArray(value.detections) &&
    value.detections.every(isDetection) &&
    Array.isArray(value.input_results) &&
    value.input_results.every(isInputResult) &&
    Array.isArray(value.content_unavailable_inputs) &&
    value.content_unavailable_inputs.every(isContentUnavailableInput) &&
    Array.isArray(value.business_context_matches) &&
    value.business_context_matches.every(isBusinessContextMatch) &&
    isNonEmptyString(value.client_request_id) &&
    isNonEmptyString(value.filter_config_revision)
  );
}

function isDetection(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonEmptyString(value.input_id) &&
    isNonNegativeFiniteNumber(value.input_index) &&
    isNonEmptyString(value.kind) &&
    isNonEmptyString(value.category) &&
    isNonEmptyString(value.type) &&
    isNonEmptyString(value.source) &&
    (value.rule_id === null || typeof value.rule_id === "string") &&
    (value.detector_id === null || typeof value.detector_id === "string") &&
    isNonEmptyString(value.severity) &&
    isDecisionAction(value.action) &&
    isNonEmptyString(value.placeholder) &&
    isNonNegativeFiniteNumber(value.confidence) &&
    isNonEmptyString(value.reason_code) &&
    isNonNegativeFiniteNumber(value.match_count)
  );
}

function isInputResult(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonEmptyString(value.input_id) &&
    isNonNegativeFiniteNumber(value.input_index) &&
    isNonEmptyString(value.kind) &&
    isNonEmptyString(value.source) &&
    typeof value.content_included === "boolean" &&
    typeof value.content_scanned === "boolean" &&
    isNonEmptyString(value.decision_basis) &&
    (value.content_unavailable_reason === undefined || isNonEmptyString(value.content_unavailable_reason)) &&
    (value.limit_exceeded === undefined || isNonEmptyString(value.limit_exceeded))
  );
}

function isContentUnavailableInput(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonEmptyString(value.input_id) &&
    isNonNegativeFiniteNumber(value.input_index) &&
    isNonEmptyString(value.kind) &&
    isNonEmptyString(value.source) &&
    isNonEmptyString(value.reason) &&
    (value.limit_exceeded === undefined || isNonEmptyString(value.limit_exceeded))
  );
}

function isBusinessContextMatch(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonEmptyString(value.input_id) &&
    isNonNegativeFiniteNumber(value.input_index) &&
    isNonEmptyString(value.kind) &&
    isNonEmptyString(value.source) &&
    isNonEmptyString(value.category) &&
    isNonEmptyString(value.reason_code) &&
    isNonNegativeFiniteNumber(value.match_count) &&
    Array.isArray(value.matched_keywords) &&
    isRecord(value.evidence_counts)
  );
}

function isDecisionAction(value: unknown): boolean {
  return value === "Allow" || value === "Warn" || value === "Mask" || value === "Block";
}

function isRiskLevel(value: unknown): boolean {
  return value === "low" || value === "medium" || value === "high" || value === "critical";
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
