import type { ExtensionConfigResponse } from "./types";

export const EXTENSION_VERSION = "0.4.0";
export const DEFAULT_POLICY_VERSION = "v0.4.0-default";
export const DEFAULT_TIMEOUT_MS = 3000;

export const DEFAULT_CONFIG: ExtensionConfigResponse = {
  api_base_url: "https://promptguard.example.com/api/v1",
  policy_version: DEFAULT_POLICY_VERSION,
  timeout_ms: DEFAULT_TIMEOUT_MS,
  ai_service_configs: [
    {
      service: "CHATGPT",
      domains: ["chatgpt.com", "chat.openai.com"],
      selectors: {
        input: ["textarea", "[contenteditable='true']"],
        send_button: ["button[data-testid='send-button']"],
        file_input: ["input[type='file']"],
        drop_zone: ["body"]
      }
    }
  ],
  file_upload: {
    enabled: true,
    max_file_size_bytes: 1_048_576,
    max_total_size_bytes: 3_145_728,
    max_file_count: 5,
    allowed_extensions: [
      ".txt",
      ".md",
      ".csv",
      ".json",
      ".yaml",
      ".yml",
      ".xml",
      ".log",
      ".env",
      ".ini",
      ".conf",
      ".sql",
      ".py",
      ".js",
      ".ts",
      ".java",
      ".go",
      ".rs"
    ],
    excluded_extensions: [".pdf", ".docx", ".xlsx", ".pptx", ".zip", ".png", ".jpg", ".jpeg"]
  }
};

export const STORAGE_KEYS = {
  apiBaseUrl: "promptguard.apiBaseUrl",
  accessToken: "promptguard.accessToken",
  refreshToken: "promptguard.refreshToken",
  configCache: "promptguard.configCache",
  lastConfigSyncAt: "promptguard.lastConfigSyncAt",
  mockMode: "promptguard.mockMode"
} as const;
