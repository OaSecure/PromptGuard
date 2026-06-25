import { refreshAccessTokenSingleFlight } from "./authenticatedApiClient";
import { getAuthState } from "./authStore";
import { getSettings } from "./configStore";
import { saveAuthTokens } from "./authStore";
import { analyzeTimeoutMs } from "../shared/configAccessors";
import { normalizeError, isNormalizedError } from "../shared/errors";
import type { AnalyzeFileKind, AnalyzeSizeBucket, NormalizedError } from "../shared/types";

/** Safe metadata returned after an encrypted temporary upload. */
export interface TempUploadResult { file_ref: string; temp_scope_id: string; file_kind: AnalyzeFileKind; mime_hint?: string; extension_hint?: string; size_bucket: AnalyzeSizeBucket; expires_at: string }

/** Uploads a file to the authenticated temporary-file boundary. */
export async function uploadTempFile(payload: { file: File; requestId: string; fileKind: AnalyzeFileKind; extension: string; mime: string }): Promise<TempUploadResult | NormalizedError> {
  const settings = await getSettings();
  const auth = await getAuthState();
  const first = await uploadTempFileOnce(payload, settings.apiBaseUrl, auth.accessToken, analyzeTimeoutMs(settings.config));
  if (!isUnauthorized(first) || !auth.refreshToken?.trim()) {
    return first;
  }

  const refreshed = await refreshAccessTokenSingleFlight(auth.refreshToken, {
    baseUrl: settings.apiBaseUrl,
    timeoutMs: analyzeTimeoutMs(settings.config),
  });
  if (isNormalizedError(refreshed)) {
    return { code: "UNAUTHORIZED", message: "Login expired. Sign in again." };
  }
  await saveAuthTokens({
    accessToken: refreshed.access_token,
    refreshToken: refreshed.refresh_token ?? auth.refreshToken,
  });
  return uploadTempFileOnce(payload, settings.apiBaseUrl, refreshed.access_token, analyzeTimeoutMs(settings.config));
}

async function uploadTempFileOnce(
  payload: { file: File; requestId: string; fileKind: AnalyzeFileKind; extension: string; mime: string },
  apiBaseUrl: string,
  accessToken: string | undefined,
  timeoutMs: number,
): Promise<TempUploadResult | NormalizedError> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  const form = new FormData();
  form.append("file", new Blob([payload.file], { type: payload.file.type }), "upload.bin");
  form.append("request_id", payload.requestId);
  form.append("file_kind", payload.fileKind);
  form.append("extension_hint", payload.extension.replace(/^\./, ""));
  form.append("mime_hint", payload.mime || "application/octet-stream");
  try {
    const response = await fetch(`${apiBaseUrl.replace(/\/+$/, "")}/files/temp`, {
      method: "POST",
      headers: {
        "X-PromptGuard-Client": "chrome-extension",
        "X-PromptGuard-Extension-Version": "0.4.0",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: form,
      signal: controller.signal,
    });
    if (!response.ok) {
      return { code: response.status === 401 ? "UNAUTHORIZED" : "VALIDATION_ERROR", message: "Temporary upload failed." };
    }
    const value = await response.json();
    return isResult(value) ? value : { code: "VALIDATION_ERROR", message: "Temporary upload response was invalid." };
  } catch (error) {
    return normalizeError(error);
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

function isUnauthorized(value: unknown): value is NormalizedError {
  return isNormalizedError(value) && value.code === "UNAUTHORIZED";
}

function isResult(value: unknown): value is TempUploadResult {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<TempUploadResult>;
  return (
    typeof candidate.file_ref === "string" &&
    /^fref_[A-Za-z0-9_-]{32,}$/.test(candidate.file_ref) &&
    typeof candidate.temp_scope_id === "string" &&
    /^tscope_[A-Za-z0-9_-]{24,}$/.test(candidate.temp_scope_id) &&
    typeof candidate.expires_at === "string"
  );
}
