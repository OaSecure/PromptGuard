import { analyzeFiles } from "./fileAnalyzeClient";
import { analyzePrompt } from "./promptAnalyzeClient";
import { saveAuthTokens } from "./authStore";
import { getSettings, saveConfig } from "./configStore";
import { mockAuthMe, mockConfig } from "./mockApi";
import { getJsonWithAuthRefresh } from "./authenticatedApiClient";
import { isExtensionConfigResponse } from "../shared/configValidation";
import { isNormalizedError } from "../shared/errors";
import type { AuthMeResponse, ExtensionConfigResponse, ExtensionMessage, NormalizedError } from "../shared/types";

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
    case "AUTH_LOGIN_REQUEST":
      await saveAuthTokens({
        accessToken: message.payload.token,
        refreshToken: message.payload.refreshToken
      });
      return { ok: true };
    case "AUTH_ME_REQUEST":
      return authMe();
    case "CONFIG_SYNC_REQUEST":
      return syncConfig();
    case "GET_CONFIG_REQUEST":
      return (await getSettings()).config;
    default:
      return { code: "UNKNOWN_ERROR", message: "Unsupported extension message." } satisfies NormalizedError;
  }
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
