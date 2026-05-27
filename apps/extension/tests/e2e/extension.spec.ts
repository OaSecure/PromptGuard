import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { DEFAULT_CONFIG, DEFAULT_POLICY_VERSION } from "../../src/shared/constants";
import { findBestInputCandidate } from "../../src/content/domDetector";
import { initializePromptGuardContentScript, shutdownPromptGuardContentScript } from "../../src/content/contentScript";
import { extractPromptText } from "../../src/content/promptExtractor";
import type { AnalyzeRequest, DecisionAction, FilesAnalyzeRequest } from "../../src/shared/types";

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
    let fileRequests = 0;
    vi.stubGlobal("chrome", {
      runtime: {
        id: "test-extension",
        sendMessage: vi.fn(async (message: { type: string; payload?: unknown }) => {
          if (message.type === "GET_CONFIG_REQUEST") {
            return DEFAULT_CONFIG;
          }
          if (message.type === "PROMPT_ANALYZE_REQUEST") {
            promptRequests += 1;
            return promptResponse("Allow", message.payload as AnalyzeRequest);
          }
          if (message.type === "FILES_ANALYZE_REQUEST") {
            fileRequests += 1;
            return filesResponse("Allow", message.payload as FilesAnalyzeRequest);
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
      value: fileListLike([new File(["hello"], "notes.txt", { type: "text/plain" })]),
      configurable: true
    });

    await initializePromptGuardContentScript(document.body);

    sendButton.click();
    await waitFor(() => submits === 1);
    expect(promptRequests).toBe(1);

    fileInput.dispatchEvent(new Event("change", { bubbles: true, cancelable: true }));
    await waitFor(() => uploadEvents === 1);
    expect(fileRequests).toBe(1);

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
    let fileRequests = 0;
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
          if (message.type === "FILES_ANALYZE_REQUEST") {
            fileRequests += 1;
            return filesResponse("Allow", message.payload as FilesAnalyzeRequest);
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
      value: fileListLike([new File(["hello"], "notes.txt", { type: "text/plain" })]),
      configurable: true
    });

    const initialization = initializePromptGuardContentScript(document.body);

    sendButton.click();
    await waitFor(() => submits === 1);
    expect(promptRequests).toBe(1);

    fileInput.dispatchEvent(new Event("change", { bubbles: true, cancelable: true }));
    await waitFor(() => uploadEvents === 1);
    expect(fileRequests).toBe(1);

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
    rerenderPromptComposer();

    const replacementInput = document.querySelector<HTMLTextAreaElement>("#prompt-textarea-rerendered")!;
    const replacementButton = document.querySelector<HTMLButtonElement>("button[data-testid='send-button']")!;
    replacementInput.value = "Send after rerender";
    mockRect(replacementInput);
    replacementInput.focus();

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
    decision: {
      risk_score: 1,
      risk_level: "LOW",
      action,
      user_message: "PromptGuard decision",
      allow_original_send: action === "Allow"
    },
    detections: [],
    policy: { version: request.policy.version, latest_version: DEFAULT_POLICY_VERSION },
    partial_result: false
  };
}

function filesResponse(action: DecisionAction, request: FilesAnalyzeRequest) {
  return {
    event_id: "evt_files_fixture",
    request_id: "req_files_fixture",
    decision: {
      risk_score: 1,
      risk_level: "LOW",
      action,
      user_message: "PromptGuard file decision",
      allow_original_upload: action === "Allow"
    },
    file_results: request.files.map((file) => ({
      client_file_id: file.client_file_id,
      extension: file.extension,
      mime_type: file.mime_type,
      size_bytes: file.size_bytes,
      detections: []
    })),
    policy: { version: request.policy.version, latest_version: DEFAULT_POLICY_VERSION },
    partial_result: false
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

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (predicate()) {
      return;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 5));
  }
  expect(predicate()).toBe(true);
}
