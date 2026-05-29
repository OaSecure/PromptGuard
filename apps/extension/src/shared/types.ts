/** Policy actions that can be returned by prompt or file analysis. */
export type DecisionAction = "Allow" | "Warn" | "Mask" | "Block";
/** Risk labels used by Analyze responses and mock decisions. */
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
/** AI service surfaces supported by the MVP. */
export type AiService = "CHATGPT";
/** User interaction that started a prompt inspection request. */
export type PromptInputMethod = "CLICK" | "ENTER" | "UNKNOWN";

/** Metadata summary for one policy detection without raw detected values. */
export interface DetectionSummary {
  type: string;
  label: string;
  count: number;
  severity: "low" | "medium" | "high" | "critical";
  confidence: number;
  source: string;
}

/** Analyze decision that controls whether the original action may continue. */
export interface Decision {
  risk_score: number;
  risk_level: RiskLevel;
  action: DecisionAction;
  user_message: string;
  allow_original_send?: boolean;
  allow_original_upload?: boolean;
}

/** Prompt inspection request sent from content script to background analysis. */
export interface AnalyzeRequest {
  prompt: {
    text: string;
    input_method: PromptInputMethod;
    content_length: number;
  };
  context: ExtensionContext;
  policy: PolicyRef;
  client_request_id: string;
}

/** Prompt inspection response consumed by the prompt preflight controller. */
export interface AnalyzeResponse {
  event_id: string;
  request_id: string;
  decision: Decision;
  detections: DetectionSummary[];
  masked_prompt?: string;
  policy: PolicyStatus;
  partial_result: boolean;
}

/** Text-file inspection request sent from content script to background analysis. */
export interface FilesAnalyzeRequest {
  files: Array<{
    client_file_id: string;
    name_hash?: string;
    extension: string;
    mime_type: string;
    size_bytes: number;
    content_text: string;
  }>;
  context: ExtensionContext;
  policy: PolicyRef;
  client_request_id: string;
}

/** Per-file result metadata returned without original filenames. */
export interface FileAnalyzeResult {
  client_file_id: string;
  extension: string;
  mime_type: string;
  size_bytes: number;
  detections: DetectionSummary[];
}

/** File inspection response consumed by the upload preflight controller. */
export interface FilesAnalyzeResponse {
  event_id: string;
  request_id: string;
  decision: Decision;
  file_results: FileAnalyzeResult[];
  policy: PolicyStatus;
  partial_result: boolean;
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

/** Policy version reference used to correlate requests with server policy. */
export interface PolicyRef {
  version: string;
}

/** Policy version status returned by Analyze responses. */
export interface PolicyStatus extends PolicyRef {
  latest_version: string;
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
  };
}

/** File limits and allow/exclude lists used before reading file contents. */
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
  | "READ_TEXT_IN_MEMORY"
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
  | { type: "FILES_ANALYZE_REQUEST"; payload: FilesAnalyzeRequest }
  | { type: "FILES_ANALYZE_RESULT"; payload: FilesAnalyzeResponse | NormalizedError }
  | { type: "AUTH_LOGIN_REQUEST"; payload: { token: string; refreshToken?: string } }
  | { type: "AUTH_ME_REQUEST" }
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
