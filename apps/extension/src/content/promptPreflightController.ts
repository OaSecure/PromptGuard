import { createAnalyzeRequest, createComposerInput, createConvertedPasteInput } from "../shared/analyzeRequestBuilder";
import { analyzeTimeoutMs, filterConfigRevision } from "../shared/configAccessors";
import { createClientRequestId } from "../shared/hashing";
import type { AnalyzeInput } from "../shared/types";
import { isAnalyzeResponse } from "../shared/responseValidation";
import type { AnalyzeRequest, AnalyzeResponse, ExtensionConfigResponse, ExtensionContext, NormalizedError } from "../shared/types";
import { collectAttachmentChipInputs, resolveAttachmentChipScope } from "./attachmentChipCapture";
import { safeDecisionEvidence } from "./decisionEvidence";
import { findBestInputCandidate, type DetectorSelectors } from "./domDetector";
import { applyMaskedPrompt } from "./maskedTextInjector";
import { createPreflightOverlay, type PreflightOverlay } from "./preflightOverlay";
import { extractPromptText, type PromptInputElement } from "./promptExtractor";
import { installSendInterceptor, replaySendAttempt, type SendAttempt, type SendInterceptor } from "./sendInterceptor";

const ANALYZING_OVERLAY_DELAY_MS = 150;

/** Sends one prompt inspection request through the background boundary. */
export type PromptAnalyzeSender = (request: AnalyzeRequest) => Promise<AnalyzeResponse | NormalizedError>;

/**
 * Configures the prompt preflight controller.
 *
 * `getContext` is evaluated at send time so the request uses the current page
 * origin and browser locale without storing page-specific state in the
 * controller.
 */
export interface PromptPreflightControllerOptions {
  document?: Document;
  config: ExtensionConfigResponse;
  getContext: () => ExtensionContext;
  sendAnalyze: PromptAnalyzeSender;
  overlay?: PreflightOverlay;
}

/** Owns the lifecycle of prompt preflight hooks and UI state. */
export interface PromptPreflightController {
  disconnect(): void;
}

/**
 * Starts prompt-send inspection for the configured service selectors.
 *
 * The controller is the policy boundary between DOM events and native page
 * send behavior: it blocks first, asks Analyze, then replays only when the
 * validated decision authorizes that action.
 */
export function startPromptPreflightController(options: PromptPreflightControllerOptions): PromptPreflightController {
  const doc = options.document ?? document;
  const overlay = options.overlay ?? createPreflightOverlay(doc);
  const selectors = serviceSelectors(options.config);
  let currentAttemptId = 0;
  let analyzing = false;
  let replaying = false;
  let convertedPasteText: string | undefined;
  const requestIds = new WeakMap<SendAttempt, string>();
  const requestIdForAttempt = requestIdForAttemptFactory(requestIds);
  const resetRequestIdForAttempt = (attempt: SendAttempt): void => {
    requestIds.delete(attempt);
  };

  const getPromptInput = (): PromptInputElement | null => findBestInputCandidate(doc, { input: selectors.input })?.element ?? null;
  const handlePaste = (event: ClipboardEvent): void => {
    const promptInput = getPromptInput();
    if (!promptInput || event.target !== promptInput) {
      return;
    }
    const pasted = event.clipboardData?.getData("text/plain")?.trim();
    convertedPasteText = pasted || undefined;
  };
  doc.addEventListener("paste", handlePaste, true);

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
      overlay.show({ decision: "analyzing", message: "이미 검사 중입니다.", actions: [] });
      return;
    }

    const candidate = findBestInputCandidate(doc, { input: selectors.input });
    if (!candidate) {
      showFailClosed("전송 내용을 검사하지 못했습니다.", () => retryAttempt(attempt));
      return;
    }

    const request = buildPromptAnalyzeRequest(
      candidate.element,
      attempt.method,
      options.getContext(),
      filterConfigRevision(options.config),
      convertedPasteText,
      requestIdForAttempt(attempt),
      collectAttachmentChipInputs(resolveAttachmentChipScope(candidate.element, doc), { attachment_chip: selectors.attachment_chip })
    );
    convertedPasteText = undefined;
    recordPromptAttempt(doc, request, "inspecting");
    const composerInput = request.inputs.find((item) => item.source === "composer");
    if (!composerInput || composerInput.size_bytes === 0) {
      recordPromptStatus(doc, "error", "empty-prompt");
      showFailClosed("프롬프트를 읽지 못했습니다. 전송하지 않았습니다.", () => retryAttempt(attempt));
      return;
    }
    const attemptId = ++currentAttemptId;
    analyzing = true;
    const cancelAnalyzingOverlay = scheduleAnalyzingOverlay();

    try {
      const response = await withTimeout(options.sendAnalyze(request), analyzeTimeoutMs(options.config));
      if (attemptId !== currentAttemptId) {
        return;
      }
      if (!isAnalyzeResponse(response)) {
        recordPromptStatus(doc, "error", "invalid-response");
        showFailClosed("검사에 실패했습니다. 전송하지 않았습니다.", () => retryAttempt(attempt));
        return;
      }
      handleDecision(response, candidate.element, attempt);
    } catch {
      if (attemptId === currentAttemptId) {
        recordPromptStatus(doc, "error", "inspection-failed");
        showFailClosed("검사가 실패하거나 시간 초과되었습니다.", () => retryAttempt(attempt));
      }
    } finally {
      cancelAnalyzingOverlay();
      if (attemptId === currentAttemptId) {
        analyzing = false;
      }
    }
  }

  function scheduleAnalyzingOverlay(message = "전송 전 검사 중입니다."): () => void {
    const timeoutId = window.setTimeout(() => {
      overlay.show({ decision: "analyzing", message, actions: [] });
    }, ANALYZING_OVERLAY_DELAY_MS);
    return () => window.clearTimeout(timeoutId);
  }

  function handleDecision(response: AnalyzeResponse, input: PromptInputElement, attempt: SendAttempt): void {
    recordPromptStatus(doc, response.action.toLowerCase());
    switch (response.action) {
      case "Allow":
        if (response.allow_original_send === false) {
          showFailClosed("원문 전송이 허용되지 않았습니다.", () => retryAttempt(attempt));
          return;
        }
        overlay.hide();
        replay(attempt);
        return;
      case "Warn":
        overlay.show({
          decision: "warn",
          message: safeDecisionMessage(response),
          evidence: safeDecisionEvidence(response),
          actions: [
            {
              id: "continue",
              label: "계속",
              variant: "primary",
              onClick: () => {
                if (response.allow_original_send !== true) {
                  showFailClosed("원문 전송이 허용되지 않았습니다.", () => retryAttempt(attempt));
                  return;
                }
                replay(attempt);
              }
            },
            { id: "cancel", label: "취소", variant: "secondary", onClick: overlay.hide }
          ]
        });
        return;
      case "Mask":
        overlay.show({
          decision: "mask",
          message: safeDecisionMessage(response),
          evidence: safeDecisionEvidence(response),
          actions: [
            {
              id: "apply-mask",
              label: "마스킹 적용",
              variant: "primary",
              onClick: () => {
                const result = applyMaskedPrompt(input, response.masked_prompt);
                if (result.applied) {
                  void reinspectMaskedPrompt(input, attempt);
                } else {
                  showFailClosed("마스킹을 적용하지 못했습니다.", () => retryAttempt(attempt));
                }
              }
            },
            { id: "cancel", label: "취소", variant: "secondary", onClick: overlay.hide }
          ]
        });
        return;
      case "Block":
        overlay.show({
          decision: "block",
          message: safeDecisionMessage(response),
          evidence: safeDecisionEvidence(response),
          actions: [
            { id: "retry", label: "다시 시도", variant: "secondary", onClick: () => retryAttempt(attempt) },
            { id: "cancel", label: "취소", variant: "danger", onClick: overlay.hide }
          ]
        });
        return;
    }
  }

  async function reinspectMaskedPrompt(input: PromptInputElement, attempt: SendAttempt): Promise<void> {
    if (analyzing) {
      overlay.show({ decision: "analyzing", message: "이미 검사 중입니다.", actions: [] });
      return;
    }

    const request = buildPromptAnalyzeRequest(
      input,
      attempt.method,
      options.getContext(),
      filterConfigRevision(options.config),
      undefined,
      createClientRequestId("crq"),
      collectAttachmentChipInputs(resolveAttachmentChipScope(input, doc), { attachment_chip: selectors.attachment_chip })
    );
    const composerInput = request.inputs.find((item) => item.source === "composer");
    if (!composerInput || composerInput.size_bytes === 0) {
      recordPromptStatus(doc, "error", "empty-masked-prompt");
      showFailClosed("마스킹된 프롬프트를 읽지 못했습니다. 전송하지 않았습니다.", () => retryAttempt(attempt));
      return;
    }

    const attemptId = ++currentAttemptId;
    analyzing = true;
    recordPromptAttempt(doc, request, "reinspecting-masked");
    const cancelAnalyzingOverlay = scheduleAnalyzingOverlay("마스킹본을 다시 검사 중입니다.");

    try {
      const response = await withTimeout(options.sendAnalyze(request), analyzeTimeoutMs(options.config));
      if (attemptId !== currentAttemptId) {
        return;
      }
      if (!isAnalyzeResponse(response)) {
        recordPromptStatus(doc, "error", "invalid-masked-response");
        showFailClosed("마스킹본 검사에 실패했습니다. 전송하지 않았습니다.", () => retryAttempt(attempt));
        return;
      }
      handleMaskedDecision(response, input, attempt);
    } catch {
      if (attemptId === currentAttemptId) {
        recordPromptStatus(doc, "error", "masked-inspection-failed");
        showFailClosed("마스킹본 검사가 실패하거나 시간 초과되었습니다.", () => retryAttempt(attempt));
      }
    } finally {
      cancelAnalyzingOverlay();
      if (attemptId === currentAttemptId) {
        analyzing = false;
      }
    }
  }

  function handleMaskedDecision(response: AnalyzeResponse, input: PromptInputElement, attempt: SendAttempt): void {
    if (response.action !== "Allow") {
      handleDecision(response, input, attempt);
      return;
    }
    if (response.allow_original_send === false) {
      showFailClosed("마스킹본 전송이 허용되지 않았습니다.", () => retryAttempt(attempt));
      return;
    }
    recordPromptStatus(doc, "allow");
    overlay.show({
      decision: "mask",
      message: "마스킹본 검사가 완료되었습니다.",
      evidence: safeDecisionEvidence(response),
      actions: [
        { id: "send-masked-prompt", label: "마스킹본 전송", variant: "primary", onClick: () => replay(attempt) },
        { id: "cancel", label: "취소", variant: "secondary", onClick: overlay.hide }
      ]
    });
  }

  function replay(_attempt: SendAttempt): void {
    overlay.hide();
    // The bypass flag is scoped to the replay call so user-initiated sends
    // after this moment are inspected again.
    replaying = true;
    const replayed = replaySendAttempt(doc, selectors.send_button);
    replaying = false;
    if (!replayed) {
      showFailClosed("페이지 전송 동작을 다시 실행하지 못했습니다.", () => undefined);
    }
  }

  function showFailClosed(message: string, retry: () => void): void {
    recordPromptStatus(doc, "error");
    overlay.show({
      decision: "error",
      message,
      actions: [
        { id: "retry", label: "다시 시도", variant: "secondary", onClick: retry },
        { id: "cancel", label: "취소", variant: "danger", onClick: overlay.hide }
      ]
    });
  }

  function retryAttempt(attempt: SendAttempt): void {
    resetRequestIdForAttempt(attempt);
    void handleAttempt(attempt);
  }

  return {
    disconnect() {
      currentAttemptId += 1;
      interceptor.disconnect();
      doc.removeEventListener("paste", handlePaste, true);
      overlay.destroy();
    }
  };
}

function requestIdForAttemptFactory(requestIds: WeakMap<SendAttempt, string>) {
  return (attempt: SendAttempt): string => {
    const existing = requestIds.get(attempt);
    if (existing) {
      return existing;
    }
    const created = createClientRequestId("crq");
    requestIds.set(attempt, created);
    return created;
  };
}

function recordPromptAttempt(doc: Document, request: AnalyzeRequest, status: string): void {
  const root = doc.documentElement;
  const composerInput = request.inputs.find((item) => item.source === "composer");
  root.dataset.promptguardLastStatus = status;
  root.dataset.promptguardLastPromptLength = String(composerInput?.size_bytes ?? 0);
  root.dataset.promptguardLastInputMethod = String(composerInput?.metadata?.input_method ?? "UNKNOWN");
}

function recordPromptStatus(doc: Document, status: string, reason?: string): void {
  doc.documentElement.dataset.promptguardLastStatus = status;
  if (reason) {
    doc.documentElement.dataset.promptguardLastFailure = reason;
  }
}

function safeDecisionMessage(response: AnalyzeResponse): string {
  switch (response.action) {
    case "Warn":
      return "전송 전 확인하세요.";
    case "Mask":
      return "마스킹 후 전송하세요.";
    case "Block":
      return "민감한 내용을 제거한 뒤 다시 시도하세요.";
    case "Allow":
      return "전송할 수 있습니다.";
  }
}

/**
 * Builds the Analyze request for one prompt send attempt.
 *
 * The raw text is included only as transient request payload. The context uses
 * origin-level page metadata so URL paths, queries, and fragments do not cross
 * the extension boundary.
 */
export function buildPromptAnalyzeRequest(
  input: PromptInputElement,
  inputMethod: "CLICK" | "ENTER" | "UNKNOWN",
  context: ExtensionContext,
  policyVersion: string,
  convertedPaste?: string,
  clientRequestId?: string,
  attachmentChipInputs: AnalyzeInput[] = []
): AnalyzeRequest {
  const text = extractPromptText(input);
  const inputs = [createComposerInput({ text, inputMethod }), ...attachmentChipInputs];
  if (convertedPaste && !text.includes(convertedPaste)) {
    inputs.push(createConvertedPasteInput({ text: convertedPaste }));
  }
  return createAnalyzeRequest(
    {
      ...context,
      extension_version: context.extension_version || "0.4.0"
    },
    policyVersion,
    inputs,
    clientRequestId
  );
}

function serviceSelectors(config: ExtensionConfigResponse): DetectorSelectors & { send_button: string[]; attachment_chip: string[] } {
  const serviceConfig = config.ai_service_configs.find((item) => item.service === "CHATGPT") ?? config.ai_service_configs[0];
  return {
    input: serviceConfig.selectors.input,
    send_button: serviceConfig.selectors.send_button,
    attachment_chip: serviceConfig.selectors.attachment_chip
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
