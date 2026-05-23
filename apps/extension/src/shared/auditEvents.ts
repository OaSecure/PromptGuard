import type { AnalyzeRequest, AnalyzeResponse, FilesAnalyzeRequest, FilesAnalyzeResponse } from "./types";

/** Names the preflight surface that produced a metadata-only audit event. */
export type InspectionAuditSurface = "prompt" | "files";

/**
 * Metadata-only record for an inspection decision.
 *
 * This type is safe to persist or forward to a future dashboard because it
 * excludes raw prompt text, file content, original filenames, masked prompts,
 * server `user_message`, and detected raw values.
 */
export interface InspectionAuditEvent {
  surface: InspectionAuditSurface;
  event_id: string;
  request_id: string;
  client_request_id: string;
  action: AnalyzeResponse["decision"]["action"];
  risk_level: AnalyzeResponse["decision"]["risk_level"];
  risk_score: number;
  policy_version: string;
  latest_policy_version: string;
  partial_result: boolean;
  ai_service: string;
  ai_service_domain: string;
  page_url_origin: string;
  extension_version: string;
  detection_count: number;
  file_count?: number;
}

/** Builds a metadata-only audit event for one prompt inspection response. */
export function buildPromptInspectionAuditEvent(request: AnalyzeRequest, response: AnalyzeResponse): InspectionAuditEvent {
  return {
    surface: "prompt",
    event_id: response.event_id,
    request_id: response.request_id,
    client_request_id: request.client_request_id,
    action: response.decision.action,
    risk_level: response.decision.risk_level,
    risk_score: response.decision.risk_score,
    policy_version: response.policy.version,
    latest_policy_version: response.policy.latest_version,
    partial_result: response.partial_result,
    ai_service: request.context.ai_service,
    ai_service_domain: request.context.ai_service_domain,
    page_url_origin: request.context.page_url_origin,
    extension_version: request.context.extension_version,
    detection_count: response.detections.reduce((total, detection) => total + Math.max(0, detection.count), 0)
  };
}

/** Builds a metadata-only audit event for one text-file inspection response. */
export function buildFilesInspectionAuditEvent(request: FilesAnalyzeRequest, response: FilesAnalyzeResponse): InspectionAuditEvent {
  return {
    surface: "files",
    event_id: response.event_id,
    request_id: response.request_id,
    client_request_id: request.client_request_id,
    action: response.decision.action,
    risk_level: response.decision.risk_level,
    risk_score: response.decision.risk_score,
    policy_version: response.policy.version,
    latest_policy_version: response.policy.latest_version,
    partial_result: response.partial_result,
    ai_service: request.context.ai_service,
    ai_service_domain: request.context.ai_service_domain,
    page_url_origin: request.context.page_url_origin,
    extension_version: request.context.extension_version,
    detection_count: response.file_results.reduce(
      (total, fileResult) => total + fileResult.detections.reduce((fileTotal, detection) => fileTotal + Math.max(0, detection.count), 0),
      0
    ),
    file_count: request.files.length
  };
}
