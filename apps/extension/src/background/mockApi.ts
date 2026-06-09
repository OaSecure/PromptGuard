import { DEFAULT_CONFIG } from "../shared/constants";
import type {
  AnalyzeInput,
  AnalyzeInputResult,
  AnalyzeRequest,
  AnalyzeResponse,
  AuthMeResponse,
  ContentUnavailableInput,
  DecisionAction,
  RiskLevel
} from "../shared/types";

function riskForAction(action: DecisionAction): { score: number; level: RiskLevel; message: string } {
  switch (action) {
    case "Block":
      return { score: 92, level: "critical", message: "Policy blocks this content." };
    case "Mask":
      return { score: 72, level: "high", message: "Sensitive-looking content can be masked before sending." };
    case "Warn":
      return { score: 48, level: "medium", message: "Sensitive-looking content may be present." };
    case "Allow":
      return { score: 5, level: "low", message: "No high-risk evidence was found." };
  }
}

function actionFromRequest(request: AnalyzeRequest): DecisionAction {
  const text = request.inputs
    .filter((input) => input.kind === "text" && input.content_included && typeof input.content === "string")
    .map((input) => input.content)
    .join("\n");
  const normalized = text.toLowerCase();

  if (normalized.includes("mock:block") || normalized.includes("database_url")) {
    return "Block";
  }
  if (normalized.includes("mock:mask") || containsEmailAddress(text)) {
    return "Mask";
  }
  if (normalized.includes("mock:warn") || normalized.includes("token") || request.inputs.some((input) => input.kind === "unsupported_attachment")) {
    return "Warn";
  }
  return "Allow";
}

function maskPromptForMockAnalyze(text: string): string {
  const masked = text
    .replace(/\bmock:mask\b/gi, "[masked-trigger]")
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[masked-email]");
  return masked === text ? "[masked] content requires review" : masked;
}

function containsEmailAddress(text: string): boolean {
  return /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i.test(text);
}

/** Returns a stable mock auth identity for options-page and auth-boundary tests. */
export async function mockAuthMe(): Promise<AuthMeResponse> {
  return {
    id: "mock_user",
    workspace_id: "mock_workspace",
    email: "member@example.com",
    role: "USER",
    status: "ACTIVE"
  };
}

/** Returns the default extension config in mock mode. */
export async function mockConfig() {
  return DEFAULT_CONFIG;
}

/** Returns a deterministic mock Analyze response for prompt preflight tests. */
export async function mockPromptAnalyze(request: AnalyzeRequest): Promise<AnalyzeResponse> {
  return mockAnalyze(request);
}

/** Returns a deterministic mock Analyze response for file preflight tests. */
export async function mockFilesAnalyze(request: AnalyzeRequest): Promise<AnalyzeResponse> {
  return mockAnalyze(request);
}

function mockAnalyze(request: AnalyzeRequest): AnalyzeResponse {
  const action = actionFromRequest(request);
  const risk = riskForAction(action);
  const composerText =
    request.inputs.find((input) => input.kind === "text" && input.source === "composer" && input.content_included && typeof input.content === "string")?.content ??
    "";

  return {
    event_id: `evt_mock_${request.client_request_id}`,
    request_id: `req_mock_${request.client_request_id}`,
    action,
    checked_at: new Date().toISOString(),
    risk_score: risk.score,
    risk_level: risk.level,
    user_message: risk.message,
    allow_original_send: action === "Allow",
    requires_user_confirmation: action === "Warn",
    detections:
      action === "Allow"
        ? []
        : [
            {
              input_id: request.inputs[0]?.input_id ?? "in_mock_1",
              input_index: 0,
              kind: request.inputs[0]?.kind ?? "text",
              category: action === "Block" ? "Built-in" : "PII",
              type: action === "Block" ? "DB_CONNECTION_STRING" : "EMAIL",
              source: request.inputs[0]?.source ?? "composer",
              rule_id: null,
              detector_id: "mock_detector",
              severity: action === "Block" ? "critical" : "medium",
              action,
              placeholder: action === "Block" ? "DB_CONNECTION_STRING" : "EMAIL",
              confidence: 0.9,
              reason_code: "mock_match",
              match_count: 1
            }
          ],
    input_results: buildInputResults(request.inputs, action),
    content_unavailable_inputs: buildContentUnavailableInputs(request.inputs),
    business_context_matches: [],
    client_request_id: request.client_request_id,
    filter_config_revision: request.filter_config_revision,
    masked_prompt: action === "Mask" ? maskPromptForMockAnalyze(composerText) : undefined
  };
}

function buildInputResults(inputs: AnalyzeInput[], action: DecisionAction): AnalyzeInputResult[] {
  return inputs.map((input, index) => ({
    input_id: input.input_id,
    input_index: index,
    kind: input.kind,
    source: input.source,
    content_included: input.content_included,
    content_scanned: input.kind === "text" && input.content_included,
    decision_basis: input.content_included ? (action === "Allow" ? "no_detection" : "detection") : input.kind === "attachment_metadata" ? "metadata_only" : "content_unavailable",
    content_unavailable_reason: input.content_unavailable_reason,
    limit_exceeded: input.limit_exceeded
  }));
}

function buildContentUnavailableInputs(inputs: AnalyzeInput[]): ContentUnavailableInput[] {
  return inputs.flatMap((input, index) =>
    input.content_included || !input.content_unavailable_reason
      ? []
      : [
          {
            input_id: input.input_id,
            input_index: index,
            kind: input.kind,
            source: input.source,
            reason: input.content_unavailable_reason,
            limit_exceeded: input.limit_exceeded
          }
        ]
  );
}
