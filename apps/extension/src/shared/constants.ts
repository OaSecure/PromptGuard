import type { ExtensionConfigResponse } from "./types";

/** Current Chrome Extension package version sent on API requests. */
export const EXTENSION_VERSION = "0.4.0";
/** Default policy version used before remote config has been synced. */
export const DEFAULT_POLICY_VERSION = "v0.4.0-default";
/** Default fail-closed inspection timeout in milliseconds. */
export const DEFAULT_TIMEOUT_MS = 3000;

/**
 * Default extension config used before cached or remote config is available.
 *
 * The content script installs hooks with this config at `document_start` so
 * prompt/file attempts are protected even while background config is loading.
 */
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
        send_button: [
          "button[data-testid='send-button']",
          "button[data-testid='composer-send-button']",
          "button[data-testid*='send']",
          "button[aria-label='Send message']",
          "button[aria-label='Send prompt']",
          "button[aria-label='Send']",
          "button[aria-label*='보내기']"
        ],
        file_input: ["input[type='file']"],
        drop_zone: ["body"],
        attachment_chip: [
          "[data-promptguard-attachment-chip]",
          "[data-testid='attachment-chip']",
          "[data-testid='attachment-item']"
        ]
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

/** Storage keys used for extension-local operational settings only. */
export const STORAGE_KEYS = {
  apiBaseUrl: "promptguard.apiBaseUrl",
  accessToken: "promptguard.accessToken",
  refreshToken: "promptguard.refreshToken",
  configCache: "promptguard.configCache",
  lastConfigSyncAt: "promptguard.lastConfigSyncAt",
  mockMode: "promptguard.mockMode"
} as const;
