import { analyzeFiles } from "./fileAnalyzeClient";
import { analyzePrompt } from "./promptAnalyzeClient";
import { clearAuthState, getAuthState, saveAuthTokens } from "./authStore";
import { getSettings, saveConfig } from "./configStore";
import { mockAuthMe, mockConfig } from "./mockApi";
import { getJsonWithAuthRefresh } from "./authenticatedApiClient";
import { postJson } from "./apiClient";
import { isExtensionConfigResponse } from "../shared/configValidation";
import { isNormalizedError } from "../shared/errors";
import type { AuthLoginResponse, AuthMeResponse, ExtensionConfigResponse, ExtensionMessage, NormalizedError } from "../shared/types";
import { uploadTempFile } from "./tempFileUploadClient";

/**
 * Routes one validated extension runtime message to its background handler.
 *
 * The service worker performs message shape guarding before this boundary; this
 * router keeps prompt, file, auth, and config behavior on one explicit switch.
 */
export async function routeMessage(message: ExtensionMessage): Promise<unknown> {
  switch (message.type) {
    case "PROMPT_ANALYZE_REQUEST":
      return analyzePrompt(message.payload);
    case "FILES_ANALYZE_REQUEST":
      return analyzeFiles(message.payload);
    case "TEMP_FILE_UPLOAD_REQUEST":
      return uploadTempFile(message.payload);
    case "AUTH_LOGIN_REQUEST":
      return authLogin(message.payload);
    case "AUTH_ME_REQUEST":
      return authMe();
    case "AUTH_LOGOUT_REQUEST":
      return authLogout();
    case "CONFIG_SYNC_REQUEST":
      return syncConfig();
    case "GET_CONFIG_REQUEST":
      return (await getSettings()).config;
    default:
      return { code: "UNKNOWN_ERROR", message: "Unsupported extension message." } satisfies NormalizedError;
  }
}

async function authLogout(): Promise<{ ok: true } | NormalizedError> {
  const settings = await getSettings();
  const auth = await getAuthState();
  if (settings.mockMode || !auth.accessToken?.trim() || !auth.refreshToken?.trim()) {
    await clearAuthState();
    return { ok: true };
  }

  const response = await postJson<{ refresh_token: string }, unknown>("/auth/logout", { refresh_token: auth.refreshToken }, {
    baseUrl: settings.apiBaseUrl,
    timeoutMs: settings.config.timeout_ms,
    token: auth.accessToken
  });
  await clearAuthState();
  if (isNormalizedError(response)) {
    return response;
  }
  if (!isAuthLogoutResponse(response)) {
    return { code: "VALIDATION_ERROR", message: "Logout response could not be processed." };
  }
  return { ok: true };
}

async function authLogin(payload: { login_id: string; password: string }): Promise<{ ok: true } | NormalizedError> {
  const settings = await getSettings();
  if (settings.mockMode) {
    return { ok: true };
  }
  const credentials = {
    login_id: payload.login_id.trim(),
    password: payload.password.trim()
  };
  const response = await postJson<typeof credentials, unknown>("/auth/login", credentials, {
    baseUrl: settings.apiBaseUrl,
    timeoutMs: settings.config.timeout_ms
  });
  if (isNormalizedError(response)) {
    return response;
  }
  if (!isAuthLoginResponse(response)) {
    return { code: "VALIDATION_ERROR", message: "Login response could not be processed." };
  }
  await saveAuthTokens({
    accessToken: response.access_token,
    refreshToken: response.refresh_token
  });
  return { ok: true };
}

async function authMe(): Promise<AuthMeResponse | NormalizedError> {
  const settings = await getSettings();
  if (settings.mockMode) {
    return mockAuthMe();
  }
  return getJsonWithAuthRefresh<AuthMeResponse>("/auth/me", {
    baseUrl: settings.apiBaseUrl,
    timeoutMs: settings.config.timeout_ms
  });
}

function isAuthLogoutResponse(value: unknown): value is { ok: true } {
  return typeof value === "object" && value !== null && (value as { ok?: unknown }).ok === true;
}

function isAuthLoginResponse(value: unknown): value is AuthLoginResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    "access_token" in value &&
    "refresh_token" in value &&
    typeof (value as AuthLoginResponse).access_token === "string" &&
    (value as AuthLoginResponse).access_token.trim().length > 0 &&
    typeof (value as AuthLoginResponse).refresh_token === "string" &&
    (value as AuthLoginResponse).refresh_token.trim().length > 0
  );
}

async function syncConfig(): Promise<ExtensionConfigResponse | NormalizedError> {
  const settings = await getSettings();
  const config = settings.mockMode
    ? await mockConfig()
    : await getJsonWithAuthRefresh<ExtensionConfigResponse>("/config/extension", {
        baseUrl: settings.apiBaseUrl,
        timeoutMs: settings.config.timeout_ms
      });

  if (isNormalizedError(config)) {
    return config;
  }
  if (!isExtensionConfigResponse(config)) {
    return { code: "VALIDATION_ERROR", message: "Config response could not be processed." };
  }
  if ("policy_version" in config) {
    await saveConfig(config);
  }
  return config;
}
