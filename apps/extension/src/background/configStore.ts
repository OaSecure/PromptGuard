import { DEFAULT_CONFIG, STORAGE_KEYS } from "../shared/constants";
import { isExtensionConfigResponse } from "../shared/configValidation";
import type { ExtensionConfigResponse } from "../shared/types";

export interface StoredSettings {
  apiBaseUrl: string;
  mockMode: boolean;
  config: ExtensionConfigResponse;
  lastConfigSyncAt?: string;
}

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
    mockMode: (result[STORAGE_KEYS.mockMode] as boolean | undefined) ?? true,
    config,
    lastConfigSyncAt: result[STORAGE_KEYS.lastConfigSyncAt] as string | undefined
  };
}

export async function saveApiBaseUrl(apiBaseUrl: string): Promise<void> {
  await chrome.storage.local.set({ [STORAGE_KEYS.apiBaseUrl]: normalizeApiBaseUrl(apiBaseUrl, DEFAULT_CONFIG.api_base_url) });
}

export async function saveMockMode(mockMode: boolean): Promise<void> {
  await chrome.storage.local.set({ [STORAGE_KEYS.mockMode]: mockMode });
}

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
