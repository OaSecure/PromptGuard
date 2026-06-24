import { postJsonWithAuthRefresh } from "./authenticatedApiClient";
import { getSettings } from "./configStore";
import { mockFilesAnalyze } from "./mockApi";
import { analyzeTimeoutMs } from "../shared/configAccessors";
import type { AnalyzeRequest, AnalyzeResponse, NormalizedError } from "../shared/types";

/**
 * Analyzes contract-safe attachment inputs through mock mode or the configured real API.
 *
 * The file request already omits original filenames; this client preserves that
 * boundary while adding background-only auth and API settings.
 */
export async function analyzeFiles(request: AnalyzeRequest): Promise<AnalyzeResponse | NormalizedError> {
  const settings = await getSettings();
  if (settings.mockMode) {
    return mockFilesAnalyze(request);
  }
  return postJsonWithAuthRefresh<AnalyzeRequest, AnalyzeResponse>("/prompts/analyze", request, {
    baseUrl: settings.apiBaseUrl,
    timeoutMs: analyzeTimeoutMs(settings.config)
  });
}
