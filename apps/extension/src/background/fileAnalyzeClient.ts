import { postJson } from "./apiClient";
import { getAuthState } from "./authStore";
import { getSettings } from "./configStore";
import { mockFilesAnalyze } from "./mockApi";
import type { FilesAnalyzeRequest, FilesAnalyzeResponse, NormalizedError } from "../shared/types";

/**
 * Analyzes text-file content through mock mode or the configured real API.
 *
 * The file request already omits original filenames; this client preserves that
 * boundary while adding background-only auth and API settings.
 */
export async function analyzeFiles(request: FilesAnalyzeRequest): Promise<FilesAnalyzeResponse | NormalizedError> {
  const settings = await getSettings();
  if (settings.mockMode) {
    return mockFilesAnalyze(request);
  }
  const auth = await getAuthState();
  return postJson<FilesAnalyzeRequest, FilesAnalyzeResponse>("/files/analyze", request, {
    baseUrl: settings.apiBaseUrl,
    token: auth.accessToken,
    timeoutMs: settings.config.timeout_ms
  });
}
