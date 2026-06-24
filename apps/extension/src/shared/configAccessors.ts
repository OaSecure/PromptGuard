import type { ExtensionConfigResponse, FileUploadPolicy } from "./types";

/** Returns the config revision key required by Analyze requests. */
export function filterConfigRevision(config: ExtensionConfigResponse): string {
  return config.filter_config_revision || config.policy_version;
}

/** Returns the timeout for Analyze requests. */
export function analyzeTimeoutMs(config: ExtensionConfigResponse): number {
  return config.request_timeouts?.analyze_request_ms ?? config.timeout_ms;
}

/** Returns the timeout for config/auth/control requests. */
export function configRequestTimeoutMs(config: ExtensionConfigResponse): number {
  return config.request_timeouts?.config_request_ms ?? config.timeout_ms;
}

/** Returns the attachment policy under the current config contract. */
export function attachmentPolicy(config: ExtensionConfigResponse): FileUploadPolicy {
  return config.attachment_policy ?? config.file_upload;
}
