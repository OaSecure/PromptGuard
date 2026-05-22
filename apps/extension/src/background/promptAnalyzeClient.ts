import { postJson } from "./apiClient";
import { getAuthState } from "./authStore";
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
  const auth = await getAuthState();
  return postJson<AnalyzeRequest, AnalyzeResponse>("/prompts/analyze", request, {
    baseUrl: settings.apiBaseUrl,
    token: auth.accessToken,
    timeoutMs: settings.config.timeout_ms
  });
}
