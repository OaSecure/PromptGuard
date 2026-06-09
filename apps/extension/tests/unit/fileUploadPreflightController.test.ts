import { describe, expect, it } from "vitest";
import { DEFAULT_CONFIG, DEFAULT_POLICY_VERSION } from "../../src/shared/constants";
import { startFileUploadPreflightController } from "../../src/content/fileUploadPreflightController";
import type { AnalyzeRequest, AnalyzeResponse, DecisionAction, ExtensionContext } from "../../src/shared/types";

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
    let captured: AnalyzeRequest | undefined;
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
    expect(captured?.inputs).toHaveLength(1);
    expect(captured?.inputs[0]).toMatchObject({
      kind: "text",
      source: "file",
      size_bytes: 5,
      content: "hello"
    });
    expect(Object.keys(captured!.inputs[0])).not.toContain("name");
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

  it("sends unsupported attachments as metadata-only inputs without original filename leakage", async () => {
    const page = setupFileInput([textFile("report.pdf", "pdf", "application/pdf")]);
    let captured: AnalyzeRequest | undefined;
    const controller = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async (request) => {
        captured = request;
        return responseFor("Warn", request);
      }
    });

    dispatchChange(page.input);
    await waitFor(() => overlayDecision() === "warn");

    expect(page.uploads()).toBe(0);
    expect(captured?.inputs[0]).toMatchObject({
      kind: "unsupported_attachment",
      source: "attachment_chip",
      content_included: false
    });
    expect(JSON.stringify(captured)).not.toContain("report.pdf");
    controller.disconnect();
  });

  it("fails closed when Warn does not authorize original upload", async () => {
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
    await waitFor(() => overlayDecision() === "error");

    expect(page.uploads()).toBe(0);
    controller.disconnect();
  });

  it("replays Warn only after confirmation when original upload is authorized", async () => {
    const page = setupFileInput([textFile("notes.txt", "token-like marker", "text/plain")]);
    const controller = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async (request) => responseFor("Warn", request, true)
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
    await settle();
    expect(overlayText()).not.toContain("secret-value");
    maskController.disconnect();

    const blockPage = setupFileInput([textFile("notes.txt", "hello", "text/plain")]);
    const blockController = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async (request) => responseFor("Block", request, false, "server echoed secret-value")
    });

    dispatchChange(blockPage.input);
    await settle();
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
    await settle();
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
    await settle();
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
          input_results: [{ input_id: "file_test" }]
        }) as unknown as AnalyzeResponse
    });

    dispatchChange(page.input);
    await settle();

    expect(page.uploads()).toBe(0);
    controller.disconnect();
  });

  it("reuses the same client_request_id when the same blocked attach attempt is retried", async () => {
    const page = setupFileInput([textFile("notes.txt", "hello", "text/plain")]);
    const requestIds: string[] = [];
    let attempt = 0;
    const controller = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      sendAnalyze: async (request) => {
        requestIds.push(request.client_request_id);
        attempt += 1;
        return attempt === 1 ? ({ ...responseFor("Allow", request), input_results: [{ input_id: "broken" }] } as unknown as AnalyzeResponse) : responseFor("Allow", request);
      }
    });

    dispatchChange(page.input);
    await settle();
    clickOverlayAction("retry");
    await waitFor(() => page.uploads() === 1);

    expect(requestIds).toHaveLength(2);
    expect(requestIds[0]).toBe(requestIds[1]);
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

function responseFor(action: DecisionAction, request: AnalyzeRequest, allowOriginalUpload = action === "Allow", userMessage = "PromptGuard file decision"): AnalyzeResponse {
  return {
    event_id: "evt_file_test",
    request_id: "req_file_test",
    action,
    checked_at: "2026-06-09T00:00:00Z",
    risk_score: action === "Allow" ? 1 : 80,
    risk_level: action === "Allow" ? "low" : action === "Warn" ? "medium" : "critical",
    user_message: userMessage,
    allow_original_send: allowOriginalUpload,
    requires_user_confirmation: action === "Warn",
    detections: [],
    input_results: request.inputs.map((input, index) => ({
      input_id: input.input_id,
      input_index: index,
      kind: input.kind,
      source: input.source,
      content_included: input.content_included,
      content_scanned: input.kind === "text" && input.content_included,
      decision_basis: input.content_included ? "no_detection" : input.kind === "attachment_metadata" ? "metadata_only" : "content_unavailable",
      content_unavailable_reason: input.content_unavailable_reason,
      limit_exceeded: input.limit_exceeded
    })),
    content_unavailable_inputs: [],
    business_context_matches: [],
    client_request_id: request.client_request_id,
    filter_config_revision: DEFAULT_POLICY_VERSION
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

async function settle(): Promise<void> {
  await new Promise((resolve) => window.setTimeout(resolve, 30));
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
