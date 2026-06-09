import { describe, expect, it } from "vitest";
import { DEFAULT_CONFIG, DEFAULT_POLICY_VERSION } from "../../src/shared/constants";
import { startPromptPreflightController } from "../../src/content/promptPreflightController";
import type { AnalyzeResponse, DecisionAction, ExtensionContext } from "../../src/shared/types";

const context: ExtensionContext = {
  ai_service: "CHATGPT",
  ai_service_domain: "chatgpt.com",
  page_url_origin: "https://chatgpt.com",
  extension_version: "0.4.0",
  browser: "Chrome",
  locale: "ko-KR"
};

describe("prompt preflight controller", () => {
  it("intercepts click send and replays Allow exactly once", async () => {
    const page = setupComposer("allow case");
    const controller = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => responseFor("Allow")
    });

    page.button.click();
    await waitFor(() => page.submits() === 1);

    expect(page.submits()).toBe(1);
    expect(document.documentElement.dataset.promptguardLastStatus).toBe("allow");
    expect(overlayDecision()).toBeUndefined();
    controller.disconnect();
  });

  it("intercepts ChatGPT send buttons that expose aria-label fallback selectors", async () => {
    const page = setupComposer("aria send case", { buttonAttrs: 'aria-label="Send message"' });
    const controller = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => responseFor("Block")
    });

    page.button.click();
    await waitFor(() => overlayDecision() === "block");

    expect(page.submits()).toBe(0);
    controller.disconnect();
  });

  it("intercepts the current ChatGPT composer submit button markup", async () => {
    const page = setupComposer("current chatgpt case", {
      buttonAttrs:
        'aria-describedby="_r_6m_" interestfor="_r_6m_" id="composer-submit-button" aria-label="프롬프트 보내기" data-testid="send-button" class="composer-submit-btn composer-submit-button-color h-9 w-9" style="anchor-name: --anchor-_r_6m_;"'
    });
    const controller = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => responseFor("Block")
    });

    page.button.click();
    await waitFor(() => overlayDecision() === "block");

    expect(page.submits()).toBe(0);
    controller.disconnect();
  });

  it("fails closed when Allow does not authorize original send", async () => {
    const page = setupComposer("contradictory allow case");
    const controller = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => responseFor("Allow", undefined, false)
    });

    page.button.click();
    await waitFor(() => overlayDecision() === "error");

    expect(page.submits()).toBe(0);
    controller.disconnect();
  });

  it("prevents double-submit while an inspection is pending", async () => {
    const page = setupComposer("double click case");
    let resolveInspection: ((response: AnalyzeResponse) => void) | undefined;
    const controller = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () =>
        new Promise<AnalyzeResponse>((resolve) => {
          resolveInspection = resolve;
        })
    });

    page.button.click();
    page.button.click();
    expect(page.submits()).toBe(0);

    resolveInspection!(responseFor("Allow"));
    await waitFor(() => page.submits() === 1);

    expect(page.submits()).toBe(1);
    controller.disconnect();
  });

  it("intercepts Enter send and does not intercept Shift+Enter or IME Enter", async () => {
    const page = setupComposer("enter case");
    const controller = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => responseFor("Allow")
    });

    const shiftEnter = new KeyboardEvent("keydown", { key: "Enter", shiftKey: true, bubbles: true, cancelable: true });
    page.textarea.dispatchEvent(shiftEnter);
    expect(shiftEnter.defaultPrevented).toBe(false);

    const imeEnter = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true, isComposing: true });
    page.textarea.dispatchEvent(imeEnter);
    expect(imeEnter.defaultPrevented).toBe(false);

    const enter = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    page.textarea.dispatchEvent(enter);
    await waitFor(() => page.submits() === 1);

    expect(enter.defaultPrevented).toBe(true);
    expect(page.submits()).toBe(1);
    controller.disconnect();
  });

  it("does not intercept Enter while ChatGPT @ picker token is active", async () => {
    const page = setupComposer("@gpt");
    let analyzeCount = 0;
    const controller = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => {
        analyzeCount += 1;
        return responseFor("Mask", "[masked]");
      }
    });

    page.textarea.selectionStart = page.textarea.value.length;
    page.textarea.selectionEnd = page.textarea.value.length;
    const enter = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    page.textarea.dispatchEvent(enter);

    expect(enter.defaultPrevented).toBe(false);
    expect(analyzeCount).toBe(0);
    expect(overlayDecision()).toBeUndefined();
    controller.disconnect();
  });

  it("still intercepts Enter for email-like mask candidates", async () => {
    const page = setupComposer("contact member@example.com");
    const controller = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => responseFor("Mask", "contact [masked-email]")
    });

    page.textarea.selectionStart = page.textarea.value.length;
    page.textarea.selectionEnd = page.textarea.value.length;
    const enter = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    page.textarea.dispatchEvent(enter);
    await waitFor(() => overlayDecision() === "mask");

    expect(enter.defaultPrevented).toBe(true);
    expect(page.submits()).toBe(0);
    controller.disconnect();
  });

  it("fails closed when Warn does not authorize original send", async () => {
    const page = setupComposer("warn case");
    const controller = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => responseFor("Warn")
    });

    page.button.click();
    await waitFor(() => overlayDecision() === "warn");
    expect(page.submits()).toBe(0);

    clickOverlayAction("continue");
    await waitFor(() => overlayDecision() === "error");

    expect(page.submits()).toBe(0);
    controller.disconnect();
  });

  it("replays Warn only after confirmation when original send is authorized", async () => {
    const page = setupComposer("warn authorized case");
    const controller = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => responseFor("Warn", undefined, true)
    });

    page.button.click();
    await waitFor(() => overlayDecision() === "warn");
    expect(page.submits()).toBe(0);

    clickOverlayAction("continue");
    await waitFor(() => page.submits() === 1);

    expect(page.submits()).toBe(1);
    controller.disconnect();
  });

  it("does not render server user_message raw text in Warn, Mask, or Block overlays", async () => {
    const warnPage = setupComposer("warn raw message case");
    const warnController = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => responseFor("Warn", undefined, false, "server echoed secret-value")
    });

    warnPage.button.click();
    await waitFor(() => overlayDecision() === "warn");
    expect(overlayText()).not.toContain("secret-value");
    warnController.disconnect();

    const maskPage = setupComposer("mask raw message case");
    const maskController = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => responseFor("Mask", "[masked]", false, "server echoed secret-value")
    });

    maskPage.button.click();
    await waitFor(() => overlayDecision() === "mask");
    expect(overlayText()).not.toContain("secret-value");
    maskController.disconnect();

    const blockPage = setupComposer("block raw message case");
    const blockController = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => responseFor("Block", undefined, false, "server echoed secret-value")
    });

    blockPage.button.click();
    await waitFor(() => overlayDecision() === "block");
    expect(overlayText()).not.toContain("secret-value");
    blockController.disconnect();
  });

  it("applies Mask and sends masked text once without extra confirmation", async () => {
    const page = setupComposer("mask case");
    const controller = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => responseFor("Mask", "[masked]")
    });

    page.button.click();
    await waitFor(() => overlayDecision() === "mask");
    clickOverlayAction("apply-mask");
    await waitFor(() => page.submits() === 1);

    expect(page.textarea.value).toBe("[masked]");
    expect(page.submits()).toBe(1);
    controller.disconnect();
  });

  it("applies Mask, then requires explicit confirmation before replaying masked text when requested", async () => {
    const page = setupComposer("contact member@example.com");
    const controller = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => responseFor("Mask", "contact [masked-email]", false, "PromptGuard decision", true)
    });

    page.button.click();
    await waitFor(() => overlayDecision() === "mask");
    clickOverlayAction("apply-mask");
    await waitFor(() => overlayDecision() === "warn");

    expect(page.textarea.value).toBe("contact [masked-email]");
    expect(page.submits()).toBe(0);

    clickOverlayAction("continue");
    await waitFor(() => page.submits() === 1);

    expect(page.textarea.value).toBe("contact [masked-email]");
    expect(page.submits()).toBe(1);
    controller.disconnect();
  });

  it("fails closed for Block and timeout/error paths", async () => {
    const blockPage = setupComposer("block case");
    const blockController = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => responseFor("Block")
    });

    blockPage.button.click();
    await waitFor(() => overlayDecision() === "block");
    expect(blockPage.submits()).toBe(0);
    blockController.disconnect();

    const timeoutPage = setupComposer("timeout case");
    const timeoutController = startPromptPreflightController({
      config: { ...DEFAULT_CONFIG, timeout_ms: 1 },
      getContext: () => context,
      sendAnalyze: async () => new Promise(() => undefined)
    });

    timeoutPage.button.click();
    await waitFor(() => overlayDecision() === "error");
    expect(timeoutPage.submits()).toBe(0);
    timeoutController.disconnect();
  });

  it("fails closed for malformed Analyze responses", async () => {
    const page = setupComposer("malformed response case");
    const controller = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () =>
        ({
          ...responseFor("Allow"),
          action: "Review"
        }) as unknown as AnalyzeResponse
    });

    page.button.click();
    await waitFor(() => overlayDecision() === "error");

    expect(page.submits()).toBe(0);
    controller.disconnect();
  });

  it("reuses the same client_request_id when the same blocked send attempt is retried", async () => {
    const page = setupComposer("retry case");
    const requestIds: string[] = [];
    let attempt = 0;
    const controller = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async (request) => {
        requestIds.push(request.client_request_id);
        attempt += 1;
        return attempt === 1 ? ({ ...responseFor("Allow"), action: "Review" } as unknown as AnalyzeResponse) : responseFor("Allow");
      }
    });

    page.button.click();
    await waitFor(() => overlayDecision() === "error");
    clickOverlayAction("retry");
    await waitFor(() => page.submits() === 1);

    expect(requestIds).toHaveLength(2);
    expect(requestIds[0]).toBe(requestIds[1]);
    controller.disconnect();
  });

  it("records safe prompt diagnostics without storing raw prompt text", async () => {
    const page = setupComposer("mock:block diagnostic case");
    const controller = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => responseFor("Block")
    });

    page.button.click();
    await waitFor(() => document.documentElement.dataset.promptguardLastStatus === "block");

    expect(document.documentElement.dataset.promptguardLastPromptLength).toBe(String("mock:block diagnostic case".length));
    expect(document.documentElement.dataset.promptguardLastInputMethod).toBe("CLICK");
    expect(document.documentElement.dataset.promptguardLastMockTrigger).toBeUndefined();
    expect(JSON.stringify(document.documentElement.dataset)).not.toContain("mock:block diagnostic case");
    controller.disconnect();
  });

  it("fails closed when the selected input yields no readable prompt text", async () => {
    const page = setupComposer("");
    const controller = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => responseFor("Allow")
    });

    page.button.click();
    await waitFor(() => document.documentElement.dataset.promptguardLastFailure === "empty-prompt");

    expect(overlayDecision()).toBe("error");
    expect(page.submits()).toBe(0);
    controller.disconnect();
  });
});

function setupComposer(value: string, options: { buttonAttrs?: string } = {}) {
  const buttonAttrs = options.buttonAttrs ?? 'data-testid="send-button"';
  document.body.innerHTML = `
    <form id="composer">
      <textarea id="prompt-textarea" aria-label="Prompt"></textarea>
      <button type="submit" ${buttonAttrs}>Send</button>
    </form>
  `;
  const textarea = document.querySelector<HTMLTextAreaElement>("#prompt-textarea")!;
  const button = document.querySelector<HTMLButtonElement>("button[type='submit']")!;
  textarea.value = value;
  mockRect(textarea);
  textarea.focus();

  let submitCount = 0;
  document.querySelector("form")!.addEventListener("submit", (event) => {
    event.preventDefault();
    submitCount += 1;
  });

  return {
    textarea,
    button,
    submits: () => submitCount
  };
}

function responseFor(
  action: DecisionAction,
  maskedPrompt?: string,
  allowOriginalSend = action === "Allow",
  userMessage = "PromptGuard decision",
  requiresUserConfirmation = action === "Warn"
): AnalyzeResponse {
  return {
    event_id: "evt_test",
    request_id: "req_test",
    action,
    checked_at: "2026-06-09T00:00:00Z",
    risk_score: action === "Allow" ? 1 : 70,
    risk_level: action === "Allow" ? "low" : action === "Block" ? "critical" : "high",
    user_message: userMessage,
    allow_original_send: allowOriginalSend,
    requires_user_confirmation: requiresUserConfirmation,
    detections: [],
    input_results: [],
    content_unavailable_inputs: [],
    business_context_matches: [],
    client_request_id: "crq_test",
    filter_config_revision: DEFAULT_POLICY_VERSION,
    masked_prompt: maskedPrompt,
  };
}

function mockRect(element: Element): void {
  Object.defineProperty(element, "getBoundingClientRect", {
    value: () => ({ width: 240, height: 48, top: 0, left: 0, right: 240, bottom: 48, x: 0, y: 0, toJSON: () => ({}) }),
    configurable: true
  });
}

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (predicate()) {
      return;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 5));
  }
  expect(predicate()).toBe(true);
}

function overlayDecision(): string | undefined {
  return document.querySelector<HTMLElement>("#promptguard-preflight-overlay")?.dataset.promptguardDecision;
}

function overlayText(): string {
  return document.querySelector<HTMLElement>("#promptguard-preflight-overlay")?.textContent ?? "";
}

function clickOverlayAction(action: string): void {
  document.querySelector<HTMLButtonElement>(`#promptguard-preflight-overlay button[data-promptguard-action='${action}']`)!.click();
}
