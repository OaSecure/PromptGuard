import { postJson } from "./apiClient";
import { getAuthState } from "./authStore";
import { getSettings } from "./configStore";
import { mockPromptAnalyze } from "./mockApi";
import type { AnalyzeRequest, AnalyzeResponse, NormalizedError } from "../shared/types";

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
