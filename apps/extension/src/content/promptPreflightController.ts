import { DEFAULT_POLICY_VERSION, EXTENSION_VERSION } from "../shared/constants";
import { createClientRequestId } from "../shared/hashing";
import { isAnalyzeResponse } from "../shared/responseValidation";
import type { AnalyzeRequest, AnalyzeResponse, ExtensionConfigResponse, ExtensionContext, NormalizedError } from "../shared/types";
import { findBestInputCandidate, type DetectorSelectors } from "./domDetector";
import { applyMaskedPrompt } from "./maskedTextInjector";
import { createPreflightOverlay, type PreflightOverlay } from "./preflightOverlay";
import { extractPromptText, type PromptInputElement } from "./promptExtractor";
import { installSendInterceptor, replaySendAttempt, type SendAttempt, type SendInterceptor } from "./sendInterceptor";

export type PromptAnalyzeSender = (request: AnalyzeRequest) => Promise<AnalyzeResponse | NormalizedError>;

export interface PromptPreflightControllerOptions {
  document?: Document;
  config: ExtensionConfigResponse;
  getContext: () => ExtensionContext;
  sendAnalyze: PromptAnalyzeSender;
  overlay?: PreflightOverlay;
}

export interface PromptPreflightController {
  disconnect(): void;
}

export function startPromptPreflightController(options: PromptPreflightControllerOptions): PromptPreflightController {
  const doc = options.document ?? document;
  const overlay = options.overlay ?? createPreflightOverlay(doc);
  const selectors = serviceSelectors(options.config);
  let currentAttemptId = 0;
  let analyzing = false;
  let replaying = false;

  const getPromptInput = (): PromptInputElement | null => findBestInputCandidate(doc, { input: selectors.input })?.element ?? null;

  const interceptor: SendInterceptor = installSendInterceptor({
    document: doc,
    sendButtonSelectors: selectors.send_button,
    getPromptInput,
    shouldBypass: () => replaying,
    onSendAttempt: (attempt) => {
      void handleAttempt(attempt);
    }
  });

  async function handleAttempt(attempt: SendAttempt): Promise<void> {
    if (analyzing) {
      overlay.show({ decision: "analyzing", message: "Inspection is already running.", actions: [] });
      return;
    }

    const candidate = findBestInputCandidate(doc, { input: selectors.input });
    if (!candidate) {
      showFailClosed("PromptGuard could not inspect this send.", () => void handleAttempt(attempt));
      return;
    }

    const request = buildPromptAnalyzeRequest(candidate.element, attempt.method, options.getContext(), options.config.policy_version);
    const attemptId = ++currentAttemptId;
    analyzing = true;
    overlay.show({ decision: "analyzing", message: "Inspecting prompt before send.", actions: [] });

    try {
      const response = await withTimeout(options.sendAnalyze(request), options.config.timeout_ms);
      if (attemptId !== currentAttemptId) {
        return;
      }
      if (!isAnalyzeResponse(response)) {
        showFailClosed("Inspection failed. Prompt was not sent.", () => void handleAttempt(attempt));
        return;
      }
      handleDecision(response, candidate.element, attempt);
    } catch {
      if (attemptId === currentAttemptId) {
        showFailClosed("Inspection timed out or failed. Prompt was not sent.", () => void handleAttempt(attempt));
      }
    } finally {
      if (attemptId === currentAttemptId) {
        analyzing = false;
      }
    }
  }

  function handleDecision(response: AnalyzeResponse, input: PromptInputElement, attempt: SendAttempt): void {
    switch (response.decision.action) {
      case "Allow":
        if (response.decision.allow_original_send === false) {
          showFailClosed("Inspection did not authorize sending the original prompt.", () => void handleAttempt(attempt));
          return;
        }
        overlay.hide();
        replay(attempt);
        return;
      case "Warn":
        overlay.show({
          decision: "warn",
          message: safeDecisionMessage(response),
          actions: [
            { label: "Continue", variant: "primary", onClick: () => replay(attempt) },
            { label: "Cancel", variant: "secondary", onClick: overlay.hide }
          ]
        });
        return;
      case "Mask":
        overlay.show({
          decision: "mask",
          message: safeDecisionMessage(response),
          actions: [
            {
              label: "Apply mask",
              variant: "primary",
              onClick: () => {
                const result = applyMaskedPrompt(input, response.masked_prompt);
                if (result.applied) {
                  overlay.hide();
                } else {
                  showFailClosed("Masked replacement could not be applied.", () => void handleAttempt(attempt));
                }
              }
            },
            { label: "Cancel", variant: "secondary", onClick: overlay.hide }
          ]
        });
        return;
      case "Block":
        overlay.show({
          decision: "block",
          message: safeDecisionMessage(response),
          actions: [
            { label: "Retry", variant: "secondary", onClick: () => void handleAttempt(attempt) },
            { label: "Cancel", variant: "danger", onClick: overlay.hide }
          ]
        });
        return;
    }
  }

  function replay(_attempt: SendAttempt): void {
    overlay.hide();
    replaying = true;
    const replayed = replaySendAttempt(doc, selectors.send_button);
    replaying = false;
    if (!replayed) {
      showFailClosed("PromptGuard could not hand control back to the page.", () => undefined);
    }
  }

  function showFailClosed(message: string, retry: () => void): void {
    overlay.show({
      decision: "error",
      message,
      actions: [
        { label: "Retry", variant: "secondary", onClick: retry },
        { label: "Cancel", variant: "danger", onClick: overlay.hide }
      ]
    });
  }

  return {
    disconnect() {
      currentAttemptId += 1;
      interceptor.disconnect();
      overlay.destroy();
    }
  };
}

function safeDecisionMessage(response: AnalyzeResponse): string {
  switch (response.decision.action) {
    case "Warn":
      return "PromptGuard found content that may need review.";
    case "Mask":
      return "PromptGuard can replace sensitive-looking content before you review and send again.";
    case "Block":
      return "PromptGuard blocked this prompt based on policy.";
    case "Allow":
      return "PromptGuard allowed this prompt.";
  }
}

export function buildPromptAnalyzeRequest(
  input: PromptInputElement,
  inputMethod: AnalyzeRequest["prompt"]["input_method"],
  context: ExtensionContext,
  policyVersion = DEFAULT_POLICY_VERSION
): AnalyzeRequest {
  const text = extractPromptText(input);
  return {
    prompt: {
      text,
      input_method: inputMethod,
      content_length: text.length
    },
    context: {
      ...context,
      extension_version: context.extension_version || EXTENSION_VERSION
    },
    policy: {
      version: policyVersion || DEFAULT_POLICY_VERSION
    },
    client_request_id: createClientRequestId("crq")
  };
}

function serviceSelectors(config: ExtensionConfigResponse): DetectorSelectors & { send_button: string[] } {
  const serviceConfig = config.ai_service_configs.find((item) => item.service === "CHATGPT") ?? config.ai_service_configs[0];
  return {
    input: serviceConfig.selectors.input,
    send_button: serviceConfig.selectors.send_button
  };
}

async function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  let timeoutId: number | undefined;
  const timeout = new Promise<never>((_resolve, reject) => {
    timeoutId = window.setTimeout(() => reject(new Error("PromptGuard inspection timeout.")), timeoutMs);
  });

  try {
    return await Promise.race([promise, timeout]);
  } finally {
    if (timeoutId !== undefined) {
      window.clearTimeout(timeoutId);
    }
  }
}
