import { describe, expect, it } from "vitest";
import { isExtensionConfigResponse } from "../../src/shared/configValidation";
import { DEFAULT_CONFIG } from "../../src/shared/constants";

describe("extension config validation", () => {
  it("accepts the default extension config shape", () => {
    expect(isExtensionConfigResponse(DEFAULT_CONFIG)).toBe(true);
  });

  it("rejects partial or malformed config-like objects", () => {
    expect(isExtensionConfigResponse({ policy_version: "v-test" })).toBe(false);
    expect(isExtensionConfigResponse({ ...DEFAULT_CONFIG, timeout_ms: "3000" })).toBe(false);
    expect(isExtensionConfigResponse({ ...DEFAULT_CONFIG, ai_service_configs: [{ service: "CHATGPT" }] })).toBe(false);
    expect(isExtensionConfigResponse({ ...DEFAULT_CONFIG, file_upload: { enabled: true } })).toBe(false);
  });

  it("rejects non-positive or non-finite numeric limits", () => {
    expect(isExtensionConfigResponse({ ...DEFAULT_CONFIG, timeout_ms: 0 })).toBe(false);
    expect(isExtensionConfigResponse({ ...DEFAULT_CONFIG, timeout_ms: Number.POSITIVE_INFINITY })).toBe(false);
    expect(isExtensionConfigResponse({ ...DEFAULT_CONFIG, timeout_ms: Number.NaN })).toBe(false);
    expect(
      isExtensionConfigResponse({
        ...DEFAULT_CONFIG,
        file_upload: { ...DEFAULT_CONFIG.file_upload, max_file_size_bytes: -1 }
      })
    ).toBe(false);
    expect(
      isExtensionConfigResponse({
        ...DEFAULT_CONFIG,
        file_upload: { ...DEFAULT_CONFIG.file_upload, max_total_size_bytes: 0 }
      })
    ).toBe(false);
    expect(
      isExtensionConfigResponse({
        ...DEFAULT_CONFIG,
        file_upload: { ...DEFAULT_CONFIG.file_upload, max_file_count: Number.NaN }
      })
    ).toBe(false);
  });

  it("rejects empty config selectors and unsupported empty config surfaces", () => {
    expect(isExtensionConfigResponse({ ...DEFAULT_CONFIG, api_base_url: " " })).toBe(false);
    expect(isExtensionConfigResponse({ ...DEFAULT_CONFIG, policy_version: "" })).toBe(false);
    expect(isExtensionConfigResponse({ ...DEFAULT_CONFIG, ai_service_configs: [] })).toBe(false);
    expect(
      isExtensionConfigResponse({
        ...DEFAULT_CONFIG,
        ai_service_configs: [{ ...DEFAULT_CONFIG.ai_service_configs[0], domains: [] }]
      })
    ).toBe(false);
    expect(
      isExtensionConfigResponse({
        ...DEFAULT_CONFIG,
        ai_service_configs: [
          {
            ...DEFAULT_CONFIG.ai_service_configs[0],
            selectors: { ...DEFAULT_CONFIG.ai_service_configs[0].selectors, input: [] }
          }
        ]
      })
    ).toBe(false);
    expect(
      isExtensionConfigResponse({
        ...DEFAULT_CONFIG,
        ai_service_configs: [
          {
            ...DEFAULT_CONFIG.ai_service_configs[0],
            selectors: { ...DEFAULT_CONFIG.ai_service_configs[0].selectors, send_button: [""] }
          }
        ]
      })
    ).toBe(false);
    expect(
      isExtensionConfigResponse({
        ...DEFAULT_CONFIG,
        file_upload: { ...DEFAULT_CONFIG.file_upload, allowed_extensions: [] }
      })
    ).toBe(false);
  });
});
