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

  it("requires confirmation before replaying Warn", async () => {
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
    await waitFor(() => page.submits() === 1);

    expect(page.submits()).toBe(1);
    controller.disconnect();
  });

  it("does not render server user_message raw text in Warn or Block overlays", async () => {
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

  it("applies Mask without automatic send", async () => {
    const page = setupComposer("mask case");
    const controller = startPromptPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async () => responseFor("Mask", "[masked]")
    });

    page.button.click();
    await waitFor(() => overlayDecision() === "mask");
    clickOverlayAction("apply-mask");

    expect(page.textarea.value).toBe("[masked]");
    expect(page.submits()).toBe(0);
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
          decision: { ...responseFor("Allow").decision, action: "Review" }
        }) as unknown as AnalyzeResponse
    });

    page.button.click();
    await waitFor(() => overlayDecision() === "error");

    expect(page.submits()).toBe(0);
    controller.disconnect();
  });
});

function setupComposer(value: string) {
  document.body.innerHTML = `
    <form id="composer">
      <textarea id="prompt-textarea" aria-label="Prompt"></textarea>
      <button type="submit" data-testid="send-button">Send</button>
    </form>
  `;
  const textarea = document.querySelector<HTMLTextAreaElement>("#prompt-textarea")!;
  const button = document.querySelector<HTMLButtonElement>("button[data-testid='send-button']")!;
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

function responseFor(action: DecisionAction, maskedPrompt?: string, allowOriginalSend = action === "Allow", userMessage = "PromptGuard decision"): AnalyzeResponse {
  return {
    event_id: "evt_test",
    request_id: "req_test",
    decision: {
      risk_score: action === "Allow" ? 1 : 70,
      risk_level: action === "Allow" ? "LOW" : action === "Block" ? "CRITICAL" : "HIGH",
      action,
      user_message: userMessage,
      allow_original_send: allowOriginalSend
    },
    detections: [],
    masked_prompt: maskedPrompt,
    policy: {
      version: DEFAULT_POLICY_VERSION,
      latest_version: DEFAULT_POLICY_VERSION
    },
    partial_result: false
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
