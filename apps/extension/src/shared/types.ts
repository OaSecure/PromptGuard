/** Policy actions that can be returned by Analyze. */
export type DecisionAction = "Allow" | "Warn" | "Mask" | "Block";
/** Risk labels used by Analyze responses. */
export type RiskLevel = "low" | "medium" | "high" | "critical";
/** AI service surfaces supported by the MVP. */
export type AiService = "CHATGPT";
/** User interaction that started a prompt inspection request. */
export type PromptInputMethod = "CLICK" | "ENTER" | "UNKNOWN";
/** Unified Analyze input kinds accepted by the v3.5 API contract. */
export type AnalyzeInputKind = "text" | "file_reference" | "attachment_metadata" | "unsupported_attachment";
/** Unified Analyze input sources accepted by the v3.5 API contract. */
export type AnalyzeInputSource = "composer" | "converted_paste" | "pasted_file" | "pasted_image" | "screenshot_image" | "attached_file" | "attachment_chip";
/** Content-unavailable reasons accepted by the MVP API. */
export type ContentUnavailableReason = "oversized" | "unsupported" | "metadata_only" | "unavailable";
/** Limit-exceeded identifiers accepted by the MVP API. */
export type LimitExceededCode =
  | "MAX_ANALYZE_REQUEST_BYTES"
  | "MAX_COMPOSER_TEXT_BYTES"
  | "MAX_CONVERTED_PASTE_TEXT_BYTES";
/** Input-result decision basis values returned by the MVP API. */
export type AnalyzeDecisionBasis = "no_detection" | "detection" | "content_unavailable" | "metadata_only";
/** Coarse server-side file kind used without trusting client filenames. */
export type AnalyzeFileKind = "plain_text" | "pdf" | "image" | "office_document" | "spreadsheet" | "slide" | "code" | "unknown";
/** Coarse file size bucket; exact bytes remain runtime-only where possible. */
export type AnalyzeSizeBucket = "empty" | "small" | "medium" | "large";

/** Metadata summary for one policy detection without raw detected values. */
export interface AnalyzeDetection {
  input_id: string;
  input_index: number;
  kind: AnalyzeInputKind;
  category: string;
  type: string;
  source: AnalyzeInputSource;
  rule_id: string | null;
  detector_id: string | null;
  severity: "low" | "medium" | "high" | "critical";
  action: DecisionAction;
  placeholder: string;
  confidence: number;
  reason_code: string;
  match_count: number;
}

/** Result summary for one Analyze input item. */
export interface AnalyzeInputResult {
  input_id: string;
  input_index: number;
  kind: AnalyzeInputKind;
  source: AnalyzeInputSource;
  content_included: boolean;
  content_scanned: boolean;
  decision_basis: AnalyzeDecisionBasis;
  content_unavailable_reason?: ContentUnavailableReason;
  limit_exceeded?: LimitExceededCode;
}

/** Content-unavailable summary returned without raw content. */
export interface ContentUnavailableInput {
  input_id: string;
  input_index: number;
  kind: AnalyzeInputKind;
  source: AnalyzeInputSource;
  reason: ContentUnavailableReason;
  limit_exceeded?: LimitExceededCode;
}

/** Business-context summary returned without raw text. */
export interface BusinessContextMatch {
  input_id: string;
  input_index: number;
  kind: AnalyzeInputKind;
  source: AnalyzeInputSource;
  category: string;
  reason_code: string;
  match_count: number;
  matched_keywords: string[];
  evidence_counts: Record<string, number>;
}

/** One unified Analyze request input item. */
export interface AnalyzeInput {
  input_id: string;
  kind: AnalyzeInputKind;
  source: AnalyzeInputSource;
  size_bytes: number;
  content_included: boolean;
  content?: string;
  file_ref?: string;
  temp_scope_id?: string;
  file_kind?: AnalyzeFileKind;
  mime?: string;
  extension?: string;
  size_bucket?: AnalyzeSizeBucket;
  metadata?: Record<string, unknown>;
  content_unavailable_reason?: ContentUnavailableReason;
  limit_exceeded?: LimitExceededCode;
}

/** Unified Analyze request sent from content script to background analysis. */
export interface AnalyzeRequest {
  context: ExtensionContext;
  inputs: AnalyzeInput[];
  filter_config_revision: string;
  client_request_id: string;
}

/** Unified Analyze response consumed by prompt and file preflight controllers. */
export interface AnalyzeResponse {
  event_id: string;
  request_id: string;
  action: DecisionAction;
  checked_at: string;
  risk_score: number;
  risk_level: RiskLevel;
  user_message: string;
  allow_original_send: boolean;
  requires_user_confirmation: boolean;
  detections: AnalyzeDetection[];
  input_results: AnalyzeInputResult[];
  content_unavailable_inputs: ContentUnavailableInput[];
  business_context_matches: BusinessContextMatch[];
  client_request_id: string;
  filter_config_revision: string;
  masked_prompt?: string;
}

/** Page and extension metadata attached to inspection requests. */
export interface ExtensionContext {
  ai_service: AiService;
  ai_service_domain: string;
  page_url_origin: string;
  extension_version: string;
  browser: "Chrome";
  locale: string;
}

/** Remote or cached config that controls selectors, timeouts, and file policy. */
export interface ExtensionConfigResponse {
  api_base_url: string;
  policy_version: string;
  timeout_ms: number;
  ai_service_configs: AiServiceConfig[];
  file_upload: FileUploadPolicy;
}

/** Selector and domain config for one supported AI service. */
export interface AiServiceConfig {
  service: AiService;
  domains: string[];
  selectors: {
    input: string[];
    send_button: string[];
    file_input: string[];
    drop_zone: string[];
    attachment_chip: string[];
  };
}

/** File limits and allow/exclude lists used before upload/temp handoff. */
export interface FileUploadPolicy {
  enabled: boolean;
  max_file_size_bytes: number;
  max_total_size_bytes: number;
  max_file_count: number;
  allowed_extensions: string[];
  excluded_extensions: string[];
}

/** Auth identity response used by the options-page connection test. */
export interface AuthMeResponse {
  id: string;
  workspace_id: string;
  email: string;
  role: "USER" | "ADMIN";
  status: "ACTIVE" | "DISABLED";
}

/** Token pair returned by the backend login endpoint. */
export interface AuthLoginResponse {
  access_token: string;
  refresh_token: string;
}

/** Prompt inspection lifecycle names used by tests and state documentation. */
export type PromptInspectionState =
  | "IDLE"
  | "USER_ATTEMPT_SEND"
  | "BLOCK_NATIVE_SEND"
  | "ANALYZING"
  | "DECISION_ALLOW"
  | "DECISION_WARN"
  | "DECISION_MASK"
  | "DECISION_BLOCK"
  | "REPLAYING"
  | "ERROR";

/** File inspection lifecycle names used by tests and state documentation. */
export type FileInspectionState =
  | "IDLE"
  | "USER_ATTEMPT_ATTACH"
  | "CAPTURE_FILE_EVENT"
  | "VALIDATE_FILE_POLICY"
  | "REQUIRE_TEMP_FILE_REFERENCE"
  | "ANALYZING_FILES"
  | "FILE_ALLOW"
  | "FILE_WARN"
  | "FILE_BLOCK"
  | "REPLAY_ATTACH"
  | "REATTACH_FALLBACK"
  | "ERROR";

/** Runtime message union exchanged between content/options and background. */
export type ExtensionMessage =
  | { type: "PROMPT_ANALYZE_REQUEST"; payload: AnalyzeRequest }
  | { type: "PROMPT_ANALYZE_RESULT"; payload: AnalyzeResponse | NormalizedError }
  | { type: "FILES_ANALYZE_REQUEST"; payload: AnalyzeRequest }
  | { type: "TEMP_FILE_UPLOAD_REQUEST"; payload: { file: File; requestId: string; fileKind: AnalyzeFileKind; extension: string; mime: string } }
  | { type: "FILES_ANALYZE_RESULT"; payload: AnalyzeResponse | NormalizedError }
  | { type: "AUTH_LOGIN_REQUEST"; payload: { login_id: string; password: string } }
  | { type: "AUTH_ME_REQUEST" }
  | { type: "AUTH_LOGOUT_REQUEST" }
  | { type: "CONFIG_SYNC_REQUEST" }
  | { type: "CONFIG_SYNC_RESULT"; payload: ExtensionConfigResponse | NormalizedError }
  | { type: "GET_CONFIG_REQUEST" }
  | { type: "GET_CONFIG_RESULT"; payload: ExtensionConfigResponse | NormalizedError };

/** Safe error shape that avoids echoing raw thrown or server text. */
export interface NormalizedError {
  code: "VALIDATION_ERROR" | "NETWORK_ERROR" | "TIMEOUT" | "UNAUTHORIZED" | "SERVER_ERROR" | "UNKNOWN_ERROR";
  message: string;
  request_id?: string;
}
