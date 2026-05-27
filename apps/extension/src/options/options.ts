import { DEFAULT_CONFIG, STORAGE_KEYS } from "../shared/constants";
import { isExtensionConfigResponse } from "../shared/configValidation";
import { isNormalizedError } from "../shared/errors";
import type { AuthMeResponse, ExtensionConfigResponse, NormalizedError } from "../shared/types";

const apiBaseUrlInput = document.querySelector<HTMLInputElement>("#apiBaseUrl");
const mockModeInput = document.querySelector<HTMLInputElement>("#mockMode");
const tokenInput = document.querySelector<HTMLInputElement>("#token");
const saveSettingsButton = document.querySelector<HTMLButtonElement>("#saveSettings");
const testConnectionButton = document.querySelector<HTMLButtonElement>("#testConnection");
const syncConfigButton = document.querySelector<HTMLButtonElement>("#syncConfig");
const connectionStatus = document.querySelector<HTMLElement>("#connectionStatus");
const serverStatus = document.querySelector<HTMLElement>("#serverStatus");
const modeStatus = document.querySelector<HTMLElement>("#modeStatus");
const policyVersion = document.querySelector<HTMLElement>("#policyVersion");
const fileInspection = document.querySelector<HTMLElement>("#fileInspection");
const lastConfigSync = document.querySelector<HTMLElement>("#lastConfigSync");

/**
 * Hydrates the options UI from extension-local settings.
 *
 * Cached config is rendered only after validation so a malformed stored object
 * cannot feed bad policy or selector data back into the visible settings.
 */
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
  const mockMode = (result[STORAGE_KEYS.mockMode] as boolean | undefined) ?? true;
  setValue(apiBaseUrlInput, storedApiBaseUrl || config.api_base_url);
  if (mockModeInput) {
    mockModeInput.checked = mockMode;
  }
  renderModeStatus(mockMode);
  renderConfig(config);
  renderLastConfigSync(result[STORAGE_KEYS.lastConfigSyncAt] as string | undefined);
}

/**
 * Saves operational settings and optionally stores a trimmed bearer token.
 *
 * Token handling goes through the background router so the content script never
 * needs to touch auth state.
 */
async function saveSettings(): Promise<void> {
  setButtonBusy(saveSettingsButton, true, "Saving...");
  try {
    const settings = await persistSettings();
    renderModeStatus(settings.mockMode);
    setText(serverStatus, "Not checked after settings change");
    setText(connectionStatus, "Saved");
  } catch {
    setText(connectionStatus, "Settings could not be saved.");
  } finally {
    setButtonBusy(saveSettingsButton, false);
  }
}

async function persistSettings(): Promise<{ mockMode: boolean }> {
  const mockMode = mockModeInput?.checked ?? true;
  await chrome.storage.local.set({
    [STORAGE_KEYS.apiBaseUrl]: apiBaseUrlInput?.value.trim() || DEFAULT_CONFIG.api_base_url,
    [STORAGE_KEYS.mockMode]: mockMode
  });
  const token = tokenInput?.value.trim() ?? "";
  if (token) {
    await chrome.runtime.sendMessage({ type: "AUTH_LOGIN_REQUEST", payload: { token } });
    if (tokenInput) {
      tokenInput.value = "";
    }
  }
  return { mockMode };
}

/** Tests the mock or real auth boundary and renders the connection result. */
async function testConnection(): Promise<void> {
  setText(connectionStatus, "Testing connection...");
  setText(serverStatus, "Checking...");
  setButtonBusy(testConnectionButton, true, "Testing...");
  try {
    const settings = await persistSettings();
    renderModeStatus(settings.mockMode);
    const response = (await chrome.runtime.sendMessage({ type: "AUTH_ME_REQUEST" })) as unknown;
    if (isAuthMeResponse(response)) {
      setText(connectionStatus, `${response.status} (${response.role})`);
      setText(serverStatus, settings.mockMode ? "Mock API ready" : "Connected");
      setText(policyVersion, response.policy_version);
      return;
    }
    if (isNormalizedError(response)) {
      setText(connectionStatus, response.message);
      setText(serverStatus, "Unavailable");
      return;
    }
    setText(connectionStatus, "Connection response could not be processed.");
    setText(serverStatus, "Unknown");
  } catch {
    setText(connectionStatus, "Connection check failed.");
    setText(serverStatus, "Unavailable");
  } finally {
    setButtonBusy(testConnectionButton, false);
  }
}

/**
 * Fetches extension config through mock or real mode and refreshes the UI.
 *
 * The background side validates before caching; the options page validates
 * again before rendering because cached and remote data are both untrusted.
 */
async function syncConfig(): Promise<void> {
  setText(connectionStatus, "Syncing config...");
  setText(serverStatus, "Checking...");
  setButtonBusy(syncConfigButton, true, "Syncing...");
  try {
    const settings = await persistSettings();
    renderModeStatus(settings.mockMode);
    const response = (await chrome.runtime.sendMessage({ type: "CONFIG_SYNC_REQUEST" })) as ExtensionConfigResponse | NormalizedError;
    if (isExtensionConfigResponse(response)) {
      renderConfig(response);
      await refreshLastConfigSync();
      setText(connectionStatus, "Config synced");
      setText(serverStatus, settings.mockMode ? "Mock API ready" : "Connected");
      return;
    }
    setText(connectionStatus, response.message);
    setText(serverStatus, "Unavailable");
  } catch {
    setText(connectionStatus, "Config sync failed.");
    setText(serverStatus, "Unavailable");
  } finally {
    setButtonBusy(syncConfigButton, false);
  }
}

function renderModeStatus(mockMode: boolean): void {
  setText(modeStatus, mockMode ? "Mock API" : "Real API");
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

function setButtonBusy(button: HTMLButtonElement | null, busy: boolean, busyLabel?: string): void {
  if (!button) {
    return;
  }
  if (busy) {
    button.dataset.originalLabel = button.textContent ?? "";
    button.textContent = busyLabel ?? button.textContent;
    button.disabled = true;
    return;
  }
  button.disabled = false;
  if (Object.prototype.hasOwnProperty.call(button.dataset, "originalLabel")) {
    const originalLabel = button.dataset.originalLabel ?? "";
    button.textContent = originalLabel;
    delete button.dataset.originalLabel;
  }
}

function isAuthMeResponse(value: unknown): value is AuthMeResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    "status" in value &&
    "role" in value &&
    "policy_version" in value &&
    typeof (value as AuthMeResponse).status === "string" &&
    typeof (value as AuthMeResponse).role === "string" &&
    typeof (value as AuthMeResponse).policy_version === "string"
  );
}

saveSettingsButton?.addEventListener("click", () => void saveSettings());
testConnectionButton?.addEventListener("click", () => void testConnection());
syncConfigButton?.addEventListener("click", () => void syncConfig());

void loadSettings();
