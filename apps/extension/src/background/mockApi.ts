import { DEFAULT_CONFIG, DEFAULT_POLICY_VERSION } from "../shared/constants";
import type {
  AnalyzeRequest,
  AnalyzeResponse,
  AuthMeResponse,
  DecisionAction,
  FilesAnalyzeRequest,
  FilesAnalyzeResponse,
  RiskLevel
} from "../shared/types";

function riskForAction(action: DecisionAction): { score: number; level: RiskLevel; message: string } {
  switch (action) {
    case "Block":
      return { score: 92, level: "CRITICAL", message: "Policy blocks this content." };
    case "Mask":
      return { score: 72, level: "HIGH", message: "Sensitive-looking content can be masked before sending." };
    case "Warn":
      return { score: 48, level: "MEDIUM", message: "Sensitive-looking content may be present." };
    case "Allow":
      return { score: 5, level: "LOW", message: "No high-risk evidence was found." };
  }
}

function actionFromText(text: string): DecisionAction {
  const normalized = text.toLowerCase();
  if (normalized.includes("mock:block") || normalized.includes("database_url")) {
    return "Block";
  }
  if (normalized.includes("mock:mask") || containsEmailAddress(text)) {
    return "Mask";
  }
  if (normalized.includes("mock:warn") || normalized.includes("token")) {
    return "Warn";
  }
  return "Allow";
}

/**
 * Produces a deterministic masked prompt for local Analyze smoke tests.
 *
 * The mock backend owns this transformation so the content script can exercise
 * the same contract as the real API path: receive `masked_prompt`, apply it to
 * the page input, and leave final sending to the user.
 */
function maskPromptForMockAnalyze(text: string): string {
  let masked = text
    .replace(/\bmock:mask\b/gi, "[masked-trigger]")
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[masked-email]");

  if (masked === text) {
    return "[masked] content requires review";
  }
  return masked;
}

function containsEmailAddress(text: string): boolean {
  return /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i.test(text);
}

/** Returns a stable mock identity for options-page connection checks. */
export async function mockAuthMe(): Promise<AuthMeResponse> {
  return {
    id: "mock_user",
    workspace_id: "mock_workspace",
    email: "member@example.com",
    role: "USER",
    status: "ACTIVE"
  };
}

/** Returns the default extension config for mock-mode development. */
export async function mockConfig() {
  return DEFAULT_CONFIG;
}

/**
 * Produces a deterministic prompt Analyze response for local development.
 *
 * Trigger words let tests exercise Allow, Warn, Mask, and Block without a
 * server while keeping the response shape aligned with the real client path.
 */
export async function mockPromptAnalyze(request: AnalyzeRequest): Promise<AnalyzeResponse> {
  const action = actionFromText(request.prompt.text);
  const risk = riskForAction(action);
  return {
    event_id: `evt_mock_${request.client_request_id}`,
    request_id: `req_mock_${request.client_request_id}`,
    decision: {
      risk_score: risk.score,
      risk_level: risk.level,
      action,
      user_message: risk.message,
      allow_original_send: action === "Allow"
    },
    detections:
      action === "Allow"
        ? []
        : [
            {
              type: action === "Block" ? "SECRET_FILE_CONTEXT" : "EMAIL",
              label: action === "Block" ? "Secret candidate" : "Email candidate",
              count: 1,
              severity: action === "Block" ? "critical" : "medium",
              confidence: 0.9,
              source: "mock"
            }
          ],
    masked_prompt: action === "Mask" ? maskPromptForMockAnalyze(request.prompt.text) : undefined,
    policy: {
      version: request.policy.version,
      latest_version: DEFAULT_POLICY_VERSION
    },
    partial_result: false
  };
}

/**
 * Produces a deterministic text-file Analyze response for local development.
 *
 * The mock inspects transient request text only in memory and returns decisions
 * through generated client file IDs rather than original filenames.
 */
export async function mockFilesAnalyze(request: FilesAnalyzeRequest): Promise<FilesAnalyzeResponse> {
  const hasSecretContext = request.files.some((file) => file.extension === ".env" || file.content_text.toLowerCase().includes("database_url"));
  const hasWarningContext = request.files.some((file) => file.content_text.toLowerCase().includes("token"));
  const action: DecisionAction = hasSecretContext ? "Block" : hasWarningContext ? "Warn" : "Allow";
  const risk = riskForAction(action);
  return {
    event_id: `evt_mock_${request.client_request_id}`,
    request_id: `req_mock_${request.client_request_id}`,
    decision: {
      risk_score: risk.score,
      risk_level: risk.level,
      action,
      user_message: risk.message,
      allow_original_upload: action === "Allow"
    },
    file_results: request.files.map((file) => ({
      client_file_id: file.client_file_id,
      extension: file.extension,
      mime_type: file.mime_type,
      size_bytes: file.size_bytes,
      detections:
        action === "Block"
          ? [
              {
                type: "DB_CONNECTION_STRING",
                label: "DB connection string candidate",
                count: 1,
                severity: "critical",
                confidence: 0.9,
                source: "mock"
              }
            ]
          : []
    })),
    policy: {
      version: request.policy.version,
      latest_version: DEFAULT_POLICY_VERSION
    },
    partial_result: false
  };
}
