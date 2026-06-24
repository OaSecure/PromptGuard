import { DEFAULT_CONFIG, DEFAULT_MOCK_MODE, STORAGE_KEYS } from "../shared/constants";
import { isExtensionConfigResponse } from "../shared/configValidation";
import type { ExtensionConfigResponse } from "../shared/types";

/** Operational settings that the background worker exposes to clients. */
export interface StoredSettings {
  apiBaseUrl: string;
  mockMode: boolean;
  config: ExtensionConfigResponse;
  lastConfigSyncAt?: string;
}

/**
 * Reads extension settings with safe fallbacks.
 *
 * Cached config is trusted only after shape validation. If stored data is blank
 * or malformed, the extension falls back to `DEFAULT_CONFIG` rather than using
 * invalid selectors, timeout, or file policy values.
 */
export async function getSettings(): Promise<StoredSettings> {
  const result = await chrome.storage.local.get([
    STORAGE_KEYS.apiBaseUrl,
    STORAGE_KEYS.mockMode,
    STORAGE_KEYS.configCache,
    STORAGE_KEYS.lastConfigSyncAt
  ]);
  const cachedConfig = result[STORAGE_KEYS.configCache];
  const config = isExtensionConfigResponse(cachedConfig) ? cachedConfig : DEFAULT_CONFIG;
  const configApiBaseUrl = normalizeApiBaseUrl(config.api_base_url, DEFAULT_CONFIG.api_base_url);
  const apiBaseUrl = normalizeApiBaseUrl(result[STORAGE_KEYS.apiBaseUrl], configApiBaseUrl);
  return {
    apiBaseUrl,
    mockMode: (result[STORAGE_KEYS.mockMode] as boolean | undefined) ?? DEFAULT_MOCK_MODE,
    config,
    lastConfigSyncAt: result[STORAGE_KEYS.lastConfigSyncAt] as string | undefined
  };
}

/** Saves the API base URL after trimming blank input back to the default. */
export async function saveApiBaseUrl(apiBaseUrl: string): Promise<void> {
  await chrome.storage.local.set({ [STORAGE_KEYS.apiBaseUrl]: normalizeApiBaseUrl(apiBaseUrl, DEFAULT_CONFIG.api_base_url) });
}

/** Saves whether background clients should use mock responses or real HTTP. */
export async function saveMockMode(mockMode: boolean): Promise<void> {
  await chrome.storage.local.set({ [STORAGE_KEYS.mockMode]: mockMode });
}

/**
 * Caches a validated extension config and records the sync time.
 *
 * Callers validate before saving so every cached config read can stay on the
 * same trusted shape boundary.
 */
export async function saveConfig(config: ExtensionConfigResponse): Promise<void> {
  await chrome.storage.local.set({
    [STORAGE_KEYS.configCache]: config,
    [STORAGE_KEYS.lastConfigSyncAt]: new Date().toISOString()
  });
}

function normalizeApiBaseUrl(value: unknown, fallback: string): string {
  const trimmed = typeof value === "string" ? value.trim() : "";
  return trimmed || fallback;
}
