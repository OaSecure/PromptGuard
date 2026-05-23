import { describe, expect, it } from "vitest";
import { DEFAULT_CONFIG, DEFAULT_POLICY_VERSION } from "../../src/shared/constants";
import { startFileUploadPreflightController } from "../../src/content/fileUploadPreflightController";
import type { DecisionAction, ExtensionContext, FilesAnalyzeRequest, FilesAnalyzeResponse } from "../../src/shared/types";

const context: ExtensionContext = {
  ai_service: "CHATGPT",
  ai_service_domain: "chatgpt.com",
  page_url_origin: "https://chatgpt.com",
  extension_version: "0.4.0",
  browser: "Chrome",
  locale: "ko-KR"
};

describe("file upload preflight controller", () => {
  it("intercepts file input change, sends request without original filename, and replays Allow once", async () => {
    const page = setupFileInput([textFile("notes.txt", "hello", "text/plain")]);
    let captured: FilesAnalyzeRequest | undefined;
    const controller = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async (request) => {
        captured = request;
        return responseFor("Allow", request);
      }
    });

    dispatchChange(page.input);
    await waitFor(() => page.uploads() === 1);

    expect(page.uploads()).toBe(1);
    expect(captured?.files).toHaveLength(1);
    expect(captured?.files[0]).toMatchObject({
      extension: ".txt",
      mime_type: "text/plain",
      size_bytes: 5,
      content_text: "hello"
    });
    expect(Object.keys(captured!.files[0])).not.toContain("name");
    expect(JSON.stringify(captured)).not.toContain("notes.txt");
    controller.disconnect();
  });

  it("fails closed when Allow does not authorize original upload", async () => {
    const page = setupFileInput([textFile("notes.txt", "hello", "text/plain")]);
    const controller = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async (request) => responseFor("Allow", request, false)
    });

    dispatchChange(page.input);
    await waitFor(() => overlayDecision() === "error");

    expect(page.uploads()).toBe(0);
    controller.disconnect();
  });

  it("rejects unsupported files before reading or sending", async () => {
    const page = setupFileInput([textFile("report.pdf", "pdf", "application/pdf")]);
    let calls = 0;
    const controller = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async (request) => {
        calls += 1;
        return responseFor("Allow", request);
      }
    });

    dispatchChange(page.input);
    await waitFor(() => overlayDecision() === "block");

    expect(page.uploads()).toBe(0);
    expect(calls).toBe(0);
    controller.disconnect();
  });

  it("requires confirmation before replaying Warn", async () => {
    const page = setupFileInput([textFile("notes.txt", "token-like marker", "text/plain")]);
    const controller = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async (request) => responseFor("Warn", request)
    });

    dispatchChange(page.input);
    await waitFor(() => overlayDecision() === "warn");
    expect(page.uploads()).toBe(0);

    clickOverlayAction("continue");
    await waitFor(() => page.uploads() === 1);

    expect(page.uploads()).toBe(1);
    controller.disconnect();
  });

  it("does not render server user_message raw text in Warn, Mask, or Block overlays", async () => {
    const warnPage = setupFileInput([textFile("notes.txt", "hello", "text/plain")]);
    const warnController = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async (request) => responseFor("Warn", request, false, "server echoed secret-value")
    });

    dispatchChange(warnPage.input);
    await waitFor(() => overlayDecision() === "warn");
    expect(overlayText()).not.toContain("secret-value");
    warnController.disconnect();

    const maskPage = setupFileInput([textFile("notes.txt", "hello", "text/plain")]);
    const maskController = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async (request) => responseFor("Mask", request, false, "server echoed secret-value")
    });

    dispatchChange(maskPage.input);
    await waitFor(() => overlayDecision() === "block");
    expect(overlayText()).not.toContain("secret-value");
    maskController.disconnect();

    const blockPage = setupFileInput([textFile("notes.txt", "hello", "text/plain")]);
    const blockController = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async (request) => responseFor("Block", request, false, "server echoed secret-value")
    });

    dispatchChange(blockPage.input);
    await waitFor(() => overlayDecision() === "block");
    expect(overlayText()).not.toContain("secret-value");
    blockController.disconnect();
  });

  it("fails closed for Block and timeout", async () => {
    const blockPage = setupFileInput([textFile("notes.txt", "blocked", "text/plain")]);
    const blockController = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async (request) => responseFor("Block", request)
    });

    dispatchChange(blockPage.input);
    await waitFor(() => overlayDecision() === "block");
    expect(blockPage.uploads()).toBe(0);
    blockController.disconnect();

    const timeoutPage = setupFileInput([textFile("notes.txt", "slow", "text/plain")]);
    const timeoutController = startFileUploadPreflightController({
      config: { ...DEFAULT_CONFIG, timeout_ms: 1 },
      getContext: () => context,
      sendAnalyze: async () => new Promise(() => undefined)
    });

    dispatchChange(timeoutPage.input);
    await waitFor(() => overlayDecision() === "error");
    expect(timeoutPage.uploads()).toBe(0);
    timeoutController.disconnect();
  });

  it("intercepts file drops and ignores non-file drops", async () => {
    document.body.innerHTML = `<div data-testid="drop-zone"></div>`;
    const dropZone = document.querySelector<HTMLElement>("[data-testid='drop-zone']")!;
    let calls = 0;
    const controller = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async (request) => {
        calls += 1;
        return responseFor("Allow", request);
      }
    });

    const nonFileDrop = dropEvent([]);
    dropZone.dispatchEvent(nonFileDrop);
    expect(nonFileDrop.defaultPrevented).toBe(false);

    const fileDrop = dropEvent([textFile("notes.txt", "hello", "text/plain")]);
    dropZone.dispatchEvent(fileDrop);
    await waitFor(() => calls === 1);

    expect(fileDrop.defaultPrevented).toBe(true);
    await waitFor(() => overlayDecision() === "error");
    expect(overlayText()).toContain("Please attach the files again");
    expect(overlayText()).toContain("did not allow automatic reattach");
    controller.disconnect();
  });

  it("fails closed for malformed files Analyze responses", async () => {
    const page = setupFileInput([textFile("notes.txt", "hello", "text/plain")]);
    const controller = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async (request) =>
        ({
          ...responseFor("Allow", request),
          file_results: [{ client_file_id: "file_test" }]
        }) as unknown as FilesAnalyzeResponse
    });

    dispatchChange(page.input);
    await waitFor(() => overlayDecision() === "error");

    expect(page.uploads()).toBe(0);
    controller.disconnect();
  });
});

function setupFileInput(files: File[]) {
  document.body.innerHTML = `<form><input id="file-input" type="file" multiple /></form>`;
  const input = document.querySelector<HTMLInputElement>("#file-input")!;
  Object.defineProperty(input, "files", {
    value: fileListLike(files),
    configurable: true
  });

  let uploadCount = 0;
  input.addEventListener("change", () => {
    uploadCount += 1;
  });

  return {
    input,
    uploads: () => uploadCount
  };
}

function textFile(name: string, content: string, type: string): File {
  return new File([content], name, { type });
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

function dispatchChange(input: HTMLInputElement): void {
  input.dispatchEvent(new Event("change", { bubbles: true, cancelable: true }));
}

function dropEvent(files: File[]): DragEvent {
  const event = new Event("drop", { bubbles: true, cancelable: true }) as DragEvent;
  Object.defineProperty(event, "dataTransfer", {
    value: { files: fileListLike(files) },
    configurable: true
  });
  return event;
}

function responseFor(action: DecisionAction, request: FilesAnalyzeRequest, allowOriginalUpload = action === "Allow", userMessage = "PromptGuard file decision"): FilesAnalyzeResponse {
  return {
    event_id: "evt_file_test",
    request_id: "req_file_test",
    decision: {
      risk_score: action === "Allow" ? 1 : 80,
      risk_level: action === "Allow" ? "LOW" : action === "Warn" ? "MEDIUM" : "CRITICAL",
      action,
      user_message: userMessage,
      allow_original_upload: allowOriginalUpload
    },
    file_results: request.files.map((file) => ({
      client_file_id: file.client_file_id,
      extension: file.extension,
      mime_type: file.mime_type,
      size_bytes: file.size_bytes,
      detections: []
    })),
    policy: {
      version: DEFAULT_POLICY_VERSION,
      latest_version: DEFAULT_POLICY_VERSION
    },
    partial_result: false
  };
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
