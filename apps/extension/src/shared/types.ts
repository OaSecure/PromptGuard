export type DecisionAction = "Allow" | "Warn" | "Mask" | "Block";
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type AiService = "CHATGPT";
export type PromptInputMethod = "CLICK" | "ENTER" | "UNKNOWN";

export interface DetectionSummary {
  type: string;
  label: string;
  count: number;
  severity: "low" | "medium" | "high" | "critical";
  confidence: number;
  source: string;
}

export interface Decision {
  risk_score: number;
  risk_level: RiskLevel;
  action: DecisionAction;
  user_message: string;
  allow_original_send?: boolean;
  allow_original_upload?: boolean;
}

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

export interface AnalyzeResponse {
  event_id: string;
  request_id: string;
  decision: Decision;
  detections: DetectionSummary[];
  masked_prompt?: string;
  policy: PolicyStatus;
  partial_result: boolean;
}

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

export interface FileAnalyzeResult {
  client_file_id: string;
  extension: string;
  mime_type: string;
  size_bytes: number;
  detections: DetectionSummary[];
}

export interface FilesAnalyzeResponse {
  event_id: string;
  request_id: string;
  decision: Decision;
  file_results: FileAnalyzeResult[];
  policy: PolicyStatus;
  partial_result: boolean;
}

export interface ExtensionContext {
  ai_service: AiService;
  ai_service_domain: string;
  page_url_origin: string;
  extension_version: string;
  browser: "Chrome";
  locale: string;
}

export interface PolicyRef {
  version: string;
}

export interface PolicyStatus extends PolicyRef {
  latest_version: string;
}

export interface ExtensionConfigResponse {
  api_base_url: string;
  policy_version: string;
  timeout_ms: number;
  ai_service_configs: AiServiceConfig[];
  file_upload: FileUploadPolicy;
}

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

export interface FileUploadPolicy {
  enabled: boolean;
  max_file_size_bytes: number;
  max_total_size_bytes: number;
  max_file_count: number;
  allowed_extensions: string[];
  excluded_extensions: string[];
}

export interface AuthMeResponse {
  id: string;
  workspace_id: string;
  email: string;
  role: "USER" | "ADMIN";
  status: "ACTIVE" | "DISABLED";
  policy_version: string;
}

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

export type ExtensionMessage =
  | { type: "PROMPT_ANALYZE_REQUEST"; payload: AnalyzeRequest }
  | { type: "PROMPT_ANALYZE_RESULT"; payload: AnalyzeResponse | NormalizedError }
  | { type: "FILES_ANALYZE_REQUEST"; payload: FilesAnalyzeRequest }
  | { type: "FILES_ANALYZE_RESULT"; payload: FilesAnalyzeResponse | NormalizedError }
  | { type: "AUTH_LOGIN_REQUEST"; payload: { token: string } }
  | { type: "AUTH_ME_REQUEST" }
  | { type: "CONFIG_SYNC_REQUEST" }
  | { type: "CONFIG_SYNC_RESULT"; payload: ExtensionConfigResponse | NormalizedError }
  | { type: "GET_CONFIG_REQUEST" }
  | { type: "GET_CONFIG_RESULT"; payload: ExtensionConfigResponse | NormalizedError };

export interface NormalizedError {
  code: "VALIDATION_ERROR" | "NETWORK_ERROR" | "TIMEOUT" | "UNAUTHORIZED" | "SERVER_ERROR" | "UNKNOWN_ERROR";
  message: string;
  request_id?: string;
}
