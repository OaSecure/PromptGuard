import { DEFAULT_CONFIG, STORAGE_KEYS } from "../shared/constants";
import { isExtensionConfigResponse } from "../shared/configValidation";
import type { AuthMeResponse, ExtensionConfigResponse, NormalizedError } from "../shared/types";

const apiBaseUrlInput = document.querySelector<HTMLInputElement>("#apiBaseUrl");
const mockModeInput = document.querySelector<HTMLInputElement>("#mockMode");
const tokenInput = document.querySelector<HTMLInputElement>("#token");
const saveSettingsButton = document.querySelector<HTMLButtonElement>("#saveSettings");
const testConnectionButton = document.querySelector<HTMLButtonElement>("#testConnection");
const syncConfigButton = document.querySelector<HTMLButtonElement>("#syncConfig");
const connectionStatus = document.querySelector<HTMLElement>("#connectionStatus");
const policyVersion = document.querySelector<HTMLElement>("#policyVersion");
const fileInspection = document.querySelector<HTMLElement>("#fileInspection");
const lastConfigSync = document.querySelector<HTMLElement>("#lastConfigSync");

async function loadSettings(): Promise<void> {
  const result = await chrome.storage.local.get([
    STORAGE_KEYS.apiBaseUrl,
    STORAGE_KEYS.mockMode,
    STORAGE_KEYS.configCache,
    STORAGE_KEYS.lastConfigSyncAt
  ]);
  const cachedConfig = result[STORAGE_KEYS.configCache];
  const config = isExtensionConfigResponse(cachedConfig) ? cachedConfig : DEFAULT_CONFIG;
  const storedApiBaseUrl = typeof result[STORAGE_KEYS.apiBaseUrl] === "string" ? result[STORAGE_KEYS.apiBaseUrl].trim() : "";
  setValue(apiBaseUrlInput, storedApiBaseUrl || config.api_base_url);
  if (mockModeInput) {
    mockModeInput.checked = (result[STORAGE_KEYS.mockMode] as boolean | undefined) ?? true;
  }
  renderConfig(config);
  renderLastConfigSync(result[STORAGE_KEYS.lastConfigSyncAt] as string | undefined);
}

async function saveSettings(): Promise<void> {
  await chrome.storage.local.set({
    [STORAGE_KEYS.apiBaseUrl]: apiBaseUrlInput?.value.trim() || DEFAULT_CONFIG.api_base_url,
    [STORAGE_KEYS.mockMode]: mockModeInput?.checked ?? true
  });
  const token = tokenInput?.value.trim() ?? "";
  if (token) {
    await chrome.runtime.sendMessage({ type: "AUTH_LOGIN_REQUEST", payload: { token } });
    if (tokenInput) {
      tokenInput.value = "";
    }
  }
  setText(connectionStatus, "Saved");
}

async function testConnection(): Promise<void> {
  const response = (await chrome.runtime.sendMessage({ type: "AUTH_ME_REQUEST" })) as AuthMeResponse | NormalizedError;
  if ("status" in response) {
    setText(connectionStatus, `${response.status} (${response.role})`);
    setText(policyVersion, response.policy_version);
    return;
  }
  setText(connectionStatus, response.message);
}

async function syncConfig(): Promise<void> {
  const response = (await chrome.runtime.sendMessage({ type: "CONFIG_SYNC_REQUEST" })) as ExtensionConfigResponse | NormalizedError;
  if (isExtensionConfigResponse(response)) {
    renderConfig(response);
    await refreshLastConfigSync();
    setText(connectionStatus, "Config synced");
    return;
  }
  setText(connectionStatus, response.message);
}

function renderConfig(config: ExtensionConfigResponse): void {
  setText(policyVersion, config.policy_version);
  setText(fileInspection, config.file_upload.enabled ? "Enabled" : "Disabled");
}

async function refreshLastConfigSync(): Promise<void> {
  const result = await chrome.storage.local.get(STORAGE_KEYS.lastConfigSyncAt);
  renderLastConfigSync(result[STORAGE_KEYS.lastConfigSyncAt] as string | undefined);
}

function renderLastConfigSync(value: string | undefined): void {
  if (!value) {
    setText(lastConfigSync, "Never");
    return;
  }
  const date = new Date(value);
  setText(lastConfigSync, Number.isNaN(date.getTime()) ? "Unknown" : date.toLocaleString());
}

function setValue(element: HTMLInputElement | null, value: string): void {
  if (element) {
    element.value = value;
  }
}

function setText(element: HTMLElement | null, value: string): void {
  if (element) {
    element.textContent = value;
  }
}

saveSettingsButton?.addEventListener("click", () => void saveSettings());
testConnectionButton?.addEventListener("click", () => void testConnection());
syncConfigButton?.addEventListener("click", () => void syncConfig());

void loadSettings();
