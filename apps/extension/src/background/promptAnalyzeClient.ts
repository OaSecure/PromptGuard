import { postJsonWithAuthRefresh } from "./authenticatedApiClient";
import { getSettings } from "./configStore";
import { mockPromptAnalyze } from "./mockApi";
import type { AnalyzeRequest, AnalyzeResponse, NormalizedError } from "../shared/types";

/**
 * Analyzes a prompt through mock mode or the configured real API.
 *
 * Keeping this branch in the background worker prevents content scripts from
 * handling tokens and ensures mock and real mode share the same request shape.
 */
export async function analyzePrompt(request: AnalyzeRequest): Promise<AnalyzeResponse | NormalizedError> {
  const settings = await getSettings();
  if (settings.mockMode) {
    return mockPromptAnalyze(request);
  }
  return postJsonWithAuthRefresh<AnalyzeRequest, AnalyzeResponse>("/prompts/analyze", request, {
    baseUrl: settings.apiBaseUrl,
    timeoutMs: settings.config.timeout_ms
  });
}
