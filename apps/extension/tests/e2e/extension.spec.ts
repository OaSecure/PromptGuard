import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { DEFAULT_CONFIG, DEFAULT_POLICY_VERSION } from "../../src/shared/constants";
import { findBestInputCandidate } from "../../src/content/domDetector";
import { initializePromptGuardContentScript, shutdownPromptGuardContentScript } from "../../src/content/contentScript";
import { extractPromptText } from "../../src/content/promptExtractor";
import type { AnalyzeRequest, DecisionAction } from "../../src/shared/types";
import { pdfAttachment, pngAttachment, textAttachment } from "../fixtures/attachmentFixtures";

const __dirname = dirname(fileURLToPath(import.meta.url));

describe("ChatGPT-like fixture", () => {
  it("contains expected preflight surfaces and detects the focused prompt", () => {
    const fixture = readFileSync(resolve(__dirname, "fixtures/chatgpt-like-page.html"), "utf8");
    document.documentElement.innerHTML = fixture;

    const input = document.querySelector<HTMLTextAreaElement>("#prompt-textarea");
    input!.value = "Summarize this";
    Object.defineProperty(input, "getBoundingClientRect", {
      value: () => ({ width: 240, height: 48, top: 0, left: 0, right: 240, bottom: 48, x: 0, y: 0, toJSON: () => ({}) }),
      configurable: true
    });
    input!.focus();

    expect(document.querySelector("button[data-testid='send-button']")).toBeTruthy();
    expect(document.querySelector("input[type='file']")).toBeTruthy();
    expect(document.querySelector("[data-testid='drop-zone']")).toBeTruthy();
    expect(document.querySelector("[data-testid='attachment-chip']")).toBeTruthy();
    expect(document.querySelector("[data-testid='history-attachment-chip']")).toBeTruthy();

    const candidate = findBestInputCandidate(document);
    expect(candidate?.element).toBe(input);
    expect(extractPromptText(candidate!.element)).toBe("Summarize this");
  });

  it("wires prompt and file preflight through runtime messages", async () => {
    const fixture = readFileSync(resolve(__dirname, "fixtures/chatgpt-like-page.html"), "utf8");
    document.documentElement.innerHTML = fixture;

    const input = document.querySelector<HTMLTextAreaElement>("#prompt-textarea")!;
    const fileInput = document.querySelector<HTMLInputElement>("#file-input")!;
    const sendButton = document.querySelector<HTMLButtonElement>("button[data-testid='send-button']")!;
    const form = document.querySelector<HTMLFormElement>("#composer")!;
    input.value = "Summarize this";
    mockRect(input);
    input.focus();
    let submits = 0;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      submits += 1;
    });

    let promptRequests = 0;
    let tempUploads = 0;
    let capturedPromptRequest: AnalyzeRequest | undefined;
    vi.stubGlobal("chrome", {
      runtime: {
        id: "test-extension",
        sendMessage: vi.fn(async (message: { type: string; payload?: unknown }) => {
          if (message.type === "GET_CONFIG_REQUEST") {
            return DEFAULT_CONFIG;
          }
          if (message.type === "PROMPT_ANALYZE_REQUEST") {
            promptRequests += 1;
            capturedPromptRequest = message.payload as AnalyzeRequest;
            return promptResponse("Allow", message.payload as AnalyzeRequest);
          }
          if (message.type === "TEMP_FILE_UPLOAD_REQUEST") {
            tempUploads += 1;
            const payload = message.payload as { fileKind: string; extension: string; mime: string };
            return tempUploadResponse(tempUploads, payload);
          }
          return { code: "UNKNOWN_ERROR", message: "Unsupported test message." };
        })
      }
    });

    let uploadEvents = 0;
    fileInput.addEventListener("change", () => {
      uploadEvents += 1;
    });
    Object.defineProperty(fileInput, "files", {
      value: fileListLike([textAttachment(), pngAttachment(), pdfAttachment()]),
      configurable: true
    });

    await initializePromptGuardContentScript(document.body);

    fileInput.dispatchEvent(new Event("change", { bubbles: true, cancelable: true }));
    await waitFor(() => tempUploads === 3);
    expect(uploadEvents).toBe(1);

    sendButton.click();
    await waitFor(() => submits === 1);
    expect(promptRequests).toBe(1);
    expect(capturedPromptRequest?.inputs.some((input) => input.source === "attachment_chip")).toBe(true);
    expect(capturedPromptRequest?.inputs.filter((input) => input.source === "attachment_chip")).toHaveLength(1);
    expect(capturedPromptRequest?.inputs.filter((input) => input.kind === "file_reference")).toHaveLength(3);
    expect(JSON.stringify(capturedPromptRequest)).not.toContain("customer-secret.png");
    expect(JSON.stringify(capturedPromptRequest)).not.toContain("stale-history.zip");
    expect(JSON.stringify(capturedPromptRequest)).not.toContain("fixture-notes.txt");
    expect(JSON.stringify(capturedPromptRequest)).not.toContain("fixture-image.png");
    expect(JSON.stringify(capturedPromptRequest)).not.toContain("fixture-document.pdf");
    expect(overlayDecision()).toBeUndefined();

    shutdownPromptGuardContentScript();
    vi.unstubAllGlobals();
  });

  it("does not let a failed removed attachment poison the next text-only send", async () => {
    const fixture = readFileSync(resolve(__dirname, "fixtures/chatgpt-like-page.html"), "utf8");
    document.documentElement.innerHTML = fixture;

    const input = document.querySelector<HTMLTextAreaElement>("#prompt-textarea")!;
    const fileInput = document.querySelector<HTMLInputElement>("#file-input")!;
    const sendButton = document.querySelector<HTMLButtonElement>("button[data-testid='send-button']")!;
    const attachmentChip = document.querySelector<HTMLElement>("[data-testid='attachment-chip']")!;
    const form = document.querySelector<HTMLFormElement>("#composer")!;
    input.value = "";
    mockRect(input);
    input.focus();

    let submits = 0;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      submits += 1;
    });

    let promptRequests = 0;
    let tempUploads = 0;
    let capturedPromptRequest: AnalyzeRequest | undefined;
    vi.stubGlobal("chrome", {
      runtime: {
        id: "test-extension",
        sendMessage: vi.fn(async (message: { type: string; payload?: unknown }) => {
          if (message.type === "GET_CONFIG_REQUEST") {
            return DEFAULT_CONFIG;
          }
          if (message.type === "PROMPT_ANALYZE_REQUEST") {
            promptRequests += 1;
            capturedPromptRequest = message.payload as AnalyzeRequest;
            return promptResponse("Allow", message.payload as AnalyzeRequest);
          }
          if (message.type === "TEMP_FILE_UPLOAD_REQUEST") {
            tempUploads += 1;
            return { code: "NETWORK_ERROR", message: "upload failed" };
          }
          return { code: "UNKNOWN_ERROR", message: "Unsupported test message." };
        })
      }
    });

    Object.defineProperty(fileInput, "files", {
      value: fileListLike([pngAttachment()]),
      configurable: true
    });

    await initializePromptGuardContentScript(document.body);
    fileInput.dispatchEvent(new Event("change", { bubbles: true, cancelable: true }));
    await waitFor(() => tempUploads === 1);

    attachmentChip.remove();
    input.value = "파일은 제거했고 이 텍스트만 보내줘";
    sendButton.click();

    await waitFor(() => submits === 1);
    expect(promptRequests).toBe(1);
    expect(capturedPromptRequest?.inputs.filter((item) => item.kind === "file_reference")).toHaveLength(0);
    expect(capturedPromptRequest?.inputs.filter((item) => item.kind === "attachment_metadata")).toHaveLength(0);
    expect(capturedPromptRequest?.inputs).toEqual(expect.arrayContaining([expect.objectContaining({
      kind: "text",
      source: "composer",
      content: "파일은 제거했고 이 텍스트만 보내줘"
    })]));
    expect(overlayDecision()).toBeUndefined();

    shutdownPromptGuardContentScript();
    vi.unstubAllGlobals();
  });

  it("installs default-config prompt and file hooks before config response resolves", async () => {
    const fixture = readFileSync(resolve(__dirname, "fixtures/chatgpt-like-page.html"), "utf8");
    document.documentElement.innerHTML = fixture;

    const input = document.querySelector<HTMLTextAreaElement>("#prompt-textarea")!;
    const fileInput = document.querySelector<HTMLInputElement>("#file-input")!;
    const sendButton = document.querySelector<HTMLButtonElement>("button[data-testid='send-button']")!;
    const form = document.querySelector<HTMLFormElement>("#composer")!;
    document.querySelector("[data-testid='attachment-chip']")?.remove();
    input.value = "Send before config";
    mockRect(input);
    input.focus();

    let submits = 0;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      submits += 1;
    });

    let resolveConfig: ((config: typeof DEFAULT_CONFIG) => void) | undefined;
    let promptRequests = 0;
    let tempUploads = 0;
    vi.stubGlobal("chrome", {
      runtime: {
        id: "test-extension",
        sendMessage: vi.fn(async (message: { type: string; payload?: unknown }) => {
          if (message.type === "GET_CONFIG_REQUEST") {
            return new Promise<typeof DEFAULT_CONFIG>((resolve) => {
              resolveConfig = resolve;
            });
          }
          if (message.type === "PROMPT_ANALYZE_REQUEST") {
            promptRequests += 1;
            return promptResponse("Allow", message.payload as AnalyzeRequest);
          }
          if (message.type === "TEMP_FILE_UPLOAD_REQUEST") {
            tempUploads += 1;
            const payload = message.payload as { fileKind: string; extension: string; mime: string };
            return tempUploadResponse(tempUploads, payload);
          }
          return { code: "UNKNOWN_ERROR", message: "Unsupported test message." };
        })
      }
    });

    let uploadEvents = 0;
    fileInput.addEventListener("change", () => {
      uploadEvents += 1;
    });
    Object.defineProperty(fileInput, "files", {
      value: fileListLike([pngAttachment()]),
      configurable: true
    });

    const initialization = initializePromptGuardContentScript(document.body);

    sendButton.click();
    await waitFor(() => submits === 1);
    expect(promptRequests).toBe(1);

    fileInput.dispatchEvent(new Event("change", { bubbles: true, cancelable: true }));
    await waitFor(() => tempUploads === 1);
    expect(uploadEvents).toBe(1);
    expect(overlayDecision()).toBeUndefined();

    resolveConfig!(DEFAULT_CONFIG);
    await initialization;
    shutdownPromptGuardContentScript();
    vi.unstubAllGlobals();
  });

  it("keeps prompt preflight active after the composer input re-renders", async () => {
    const fixture = readFileSync(resolve(__dirname, "fixtures/chatgpt-like-page.html"), "utf8");
    document.documentElement.innerHTML = fixture;

    let promptRequests = 0;
    vi.stubGlobal("chrome", {
      runtime: {
        id: "test-extension",
        sendMessage: vi.fn(async (message: { type: string; payload?: unknown }) => {
          if (message.type === "GET_CONFIG_REQUEST") {
            return DEFAULT_CONFIG;
          }
          if (message.type === "PROMPT_ANALYZE_REQUEST") {
            promptRequests += 1;
            return promptResponse("Block", message.payload as AnalyzeRequest);
          }
          return { code: "UNKNOWN_ERROR", message: "Unsupported test message." };
        })
      }
    });

    await initializePromptGuardContentScript(document.body);
    await waitFor(() => document.documentElement.dataset.promptguardInputDetected === "true");
    document.documentElement.dataset.promptguardInputDetected = "stale";
    document.querySelector("[data-testid='attachment-chip']")?.remove();
    rerenderPromptComposer();

    const replacementInput = document.querySelector<HTMLTextAreaElement>("#prompt-textarea-rerendered")!;
    const replacementButton = document.querySelector<HTMLButtonElement>("button[data-testid='send-button']")!;
    replacementInput.value = "Send after rerender";
    mockRect(replacementInput);
    replacementInput.focus();

    await waitFor(() => document.documentElement.dataset.promptguardInputDetected === "true");
    replacementButton.click();

    await waitFor(() => promptRequests === 1);
    await waitFor(() => document.documentElement.dataset.promptguardLastStatus === "block");
    expect(promptRequests).toBe(1);
    expect(findBestInputCandidate(document)?.element).toBe(replacementInput);
    expect(document.documentElement.dataset.promptguardLastStatus).toBe("block");

    shutdownPromptGuardContentScript();
    vi.unstubAllGlobals();
  });
});

function mockRect(element: Element): void {
  Object.defineProperty(element, "getBoundingClientRect", {
    value: () => ({ width: 240, height: 48, top: 0, left: 0, right: 240, bottom: 48, x: 0, y: 0, toJSON: () => ({}) }),
    configurable: true
  });
}

function rerenderPromptComposer(): void {
  const composer = document.querySelector<HTMLFormElement>("#composer")!;
  document.querySelector("#prompt-textarea")!.remove();
  document.querySelector("[data-testid='send-button']")!.remove();

  const replacementInput = document.createElement("textarea");
  replacementInput.id = "prompt-textarea-rerendered";
  replacementInput.setAttribute("aria-label", "Prompt");
  replacementInput.rows = 4;

  const replacementButton = document.createElement("button");
  replacementButton.type = "submit";
  replacementButton.dataset.testid = "send-button";
  replacementButton.textContent = "Send";

  composer.prepend(replacementInput);
  composer.append(replacementButton);
}

function promptResponse(action: DecisionAction, request: AnalyzeRequest) {
  return {
    event_id: "evt_prompt_fixture",
    request_id: "req_prompt_fixture",
    action,
    checked_at: "2026-06-09T00:00:00Z",
    risk_score: 1,
    risk_level: "low",
    user_message: "PromptGuard decision",
    allow_original_send: action === "Allow",
    requires_user_confirmation: action === "Warn",
    detections: [],
    input_results: [],
    content_unavailable_inputs: [],
    business_context_matches: [],
    client_request_id: request.client_request_id,
    filter_config_revision: request.filter_config_revision
  };
}

function tempUploadResponse(index: number, payload: { fileKind: string; extension: string; mime: string }) {
  return {
    file_ref: `fref_${String(index).padStart(30, "a")}`,
    temp_scope_id: `tscope_${String(index).padStart(30, "b")}`,
    file_kind: payload.fileKind,
    extension_hint: payload.extension,
    mime_hint: payload.mime,
    size_bucket: "tiny",
    expires_at: "2026-06-25T00:00:00Z"
  };
}

function fileListLike(files: File[]): FileList {
  const list: Partial<FileList> & Record<number, File> = {
    length: files.length,
    item: (index: number) => files[index] ?? null
  };
  files.forEach((file, index) => {
    list[index] = file;
  });
  return list as FileList;
}

function overlayDecision(): string | undefined {
  return document.querySelector<HTMLElement>("#promptguard-preflight-overlay")?.dataset.promptguardDecision;
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
