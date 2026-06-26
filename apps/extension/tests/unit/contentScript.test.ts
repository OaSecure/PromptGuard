import { beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_CONFIG, DEFAULT_POLICY_VERSION } from "../../src/shared/constants";
import type { AnalyzeRequest, AnalyzeResponse } from "../../src/shared/types";
import { pdfAttachment, pngAttachment, textAttachment } from "../fixtures/attachmentFixtures";

describe("content script request context", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
    vi.stubGlobal("chrome", undefined);
    document.body.innerHTML = `
      <section id="history">
        <div
          data-promptguard-attachment-chip
          data-promptguard-extension=".zip"
          data-promptguard-mime="application/zip"
          data-promptguard-size-bytes="777"
        >
          stale-history.zip
        </div>
      </section>
      <form id="composer">
        <textarea id="prompt-textarea" aria-label="Prompt"></textarea>
        <div
          data-promptguard-attachment-chip
          data-promptguard-extension=".png"
          data-promptguard-mime="image/png"
          data-promptguard-size-bytes="2048"
          data-promptguard-attachment-kind="image"
        >
          customer-secret.png
        </div>
        <button type="submit" data-testid="send-button">Send</button>
      </form>
    `;
    document.querySelector<HTMLTextAreaElement>("#prompt-textarea")!.value = "safe prompt";
    window.history.replaceState(null, "", "/c/private-thread?token=secret#fragment");
  });

  it("uses origin-only page context and omits path/query/fragment", async () => {
    const { buildPromptAnalyzeRequest } = await import("../../src/content/contentScript");

    const request = buildPromptAnalyzeRequest("ENTER");
    const serialized = JSON.stringify(request);

    expect(request?.context.page_url_origin).toBe(window.location.origin);
    expect(request?.context.ai_service_domain).toBe(window.location.hostname);
    expect(request?.filter_config_revision).toBeTruthy();
    expect(Array.isArray(request?.inputs)).toBe(true);
    expect(request?.inputs.some((input) => input.source === "attachment_chip")).toBe(true);
    expect(request?.inputs).toHaveLength(2);
    expect(serialized).not.toContain("login_id");
    expect(serialized).not.toContain("customer-secret.png");
    expect(serialized).not.toContain("stale-history.zip");
    expect(serialized).not.toContain("private-thread");
    expect(serialized).not.toContain("token=secret");
    expect(serialized).not.toContain("fragment");
  });

  it("does not add placeholder attachment chips to harmless prompt requests", async () => {
    document.body.innerHTML = `
      <form id="composer">
        <textarea id="prompt-textarea" aria-label="Prompt"></textarea>
        <div data-testid="attachment-item"></div>
        <button type="submit" data-testid="send-button">Send</button>
      </form>
    `;
    document.querySelector<HTMLTextAreaElement>("#prompt-textarea")!.value = "안녕";

    const { buildPromptAnalyzeRequest } = await import("../../src/content/contentScript");

    const request = buildPromptAnalyzeRequest("ENTER");

    expect(request?.inputs).toHaveLength(1);
    expect(request?.inputs[0]).toMatchObject({
      kind: "text",
      source: "composer"
    });
    expect(request?.inputs.some((input) => input.kind === "unsupported_attachment")).toBe(false);
  });

  it("uploads real attachment files to temp storage and includes file_references in send-time Analyze", async () => {
    document.body.innerHTML = `
      <form id="composer">
        <textarea id="prompt-textarea" aria-label="Prompt"></textarea>
        ${attachmentChipMarkup(".pdf", "application/pdf", "8192", "file")}
        <input id="file-input" type="file" multiple />
        <button type="submit" data-testid="send-button">Send</button>
      </form>
    `;
    document.querySelector<HTMLTextAreaElement>("#prompt-textarea")!.value = "첨부 파일까지 검사해줘";
    let submitCount = 0;
    document.querySelector<HTMLFormElement>("#composer")!.addEventListener("submit", (event) => {
      event.preventDefault();
      submitCount += 1;
    });

    const uploads: Array<{ file_bytes_base64: string; fileKind: string; extension: string; mime: string; requestId: string }> = [];
    let promptAnalyze: AnalyzeRequest | undefined;
    vi.stubGlobal("chrome", {
      runtime: {
        id: "promptguard-test",
        sendMessage: vi.fn(async (message: { type: string; payload?: unknown }) => {
          if (message.type === "GET_CONFIG_REQUEST") {
            return DEFAULT_CONFIG;
          }
          if (message.type === "TEMP_FILE_UPLOAD_REQUEST") {
            const payload = message.payload as { file_bytes_base64: string; fileKind: string; extension: string; mime: string; requestId: string };
            uploads.push(payload);
            return {
              file_ref: `fref_${uploads.length.toString().padStart(30, "a")}`,
              temp_scope_id: `tscope_${uploads.length.toString().padStart(30, "b")}`,
              file_kind: payload.fileKind,
              extension_hint: payload.extension,
              mime_hint: payload.mime,
              size_bucket: "tiny",
              expires_at: "2026-06-25T00:00:00Z"
            };
          }
          if (message.type === "PROMPT_ANALYZE_REQUEST") {
            promptAnalyze = message.payload as AnalyzeRequest;
            return responseFor(promptAnalyze);
          }
          return {};
        })
      }
    });

    const { initializePromptGuardContentScript, shutdownPromptGuardContentScript } = await import("../../src/content/contentScript");
    await initializePromptGuardContentScript(document.body);

    const input = document.querySelector<HTMLInputElement>("#file-input")!;
    Object.defineProperty(input, "files", {
      value: fileListLike([textAttachment(), pngAttachment(), pdfAttachment()]),
      configurable: true
    });
    input.dispatchEvent(new Event("change", { bubbles: true, cancelable: true }));
    await waitFor(() => uploads.length === 3);

    document.querySelector<HTMLButtonElement>("button[type='submit']")!.click();
    await waitFor(() => submitCount === 1);

    expect(uploads.map((upload) => upload.fileKind)).toEqual(["plain_text", "image", "pdf"]);
    expect(uploads.map((upload) => upload.mime)).toEqual(["text/plain", "image/png", "application/pdf"]);
    expect(uploads.every((upload) => upload.file_bytes_base64.length > 0)).toBe(true);
    expect(new Set(uploads.map((upload) => upload.requestId)).size).toBe(1);
    expect(promptAnalyze?.client_request_id).toBe(uploads[0].requestId);
    expect(promptAnalyze?.inputs.filter((input) => input.kind === "file_reference")).toHaveLength(3);
    expect(JSON.stringify(promptAnalyze)).not.toContain("fixture-notes.txt");
    expect(JSON.stringify(promptAnalyze)).not.toContain("fixture-image.png");
    expect(JSON.stringify(promptAnalyze)).not.toContain("fixture-document.pdf");
    shutdownPromptGuardContentScript();
  });

  it("sends file-only Analyze requests when the composer text is empty", async () => {
    document.body.innerHTML = `
      <form id="composer">
        <textarea id="prompt-textarea" aria-label="Prompt"></textarea>
        ${attachmentChipMarkup(".pdf", "application/pdf", "8192", "file")}
        <input id="file-input" type="file" multiple />
        <button type="submit" data-testid="send-button">Send</button>
      </form>
    `;
    let submitCount = 0;
    document.querySelector<HTMLFormElement>("#composer")!.addEventListener("submit", (event) => {
      event.preventDefault();
      submitCount += 1;
    });

    let promptAnalyze: AnalyzeRequest | undefined;
    let tempUploadRequestId: string | undefined;
    let tempUploads = 0;
    vi.stubGlobal("chrome", {
      runtime: {
        id: "promptguard-test",
        sendMessage: vi.fn(async (message: { type: string; payload?: unknown }) => {
          if (message.type === "GET_CONFIG_REQUEST") {
            return DEFAULT_CONFIG;
          }
          if (message.type === "TEMP_FILE_UPLOAD_REQUEST") {
            tempUploads += 1;
            const payload = message.payload as { fileKind: string; extension: string; mime: string; requestId: string };
            tempUploadRequestId = payload.requestId;
            return {
              file_ref: "fref_fileonlyabcdefghijklmnopqrstuvwxyz",
              temp_scope_id: "tscope_fileonlyabcdefghijklmnopqrstuv",
              file_kind: payload.fileKind,
              extension_hint: payload.extension,
              mime_hint: payload.mime,
              size_bucket: "tiny",
              expires_at: "2026-06-25T00:00:00Z"
            };
          }
          if (message.type === "PROMPT_ANALYZE_REQUEST") {
            promptAnalyze = message.payload as AnalyzeRequest;
            return responseFor(promptAnalyze);
          }
          return {};
        })
      }
    });

    const { initializePromptGuardContentScript, shutdownPromptGuardContentScript } = await import("../../src/content/contentScript");
    await initializePromptGuardContentScript(document.body);

    const input = document.querySelector<HTMLInputElement>("#file-input")!;
    Object.defineProperty(input, "files", {
      value: fileListLike([pdfAttachment()]),
      configurable: true
    });
    input.dispatchEvent(new Event("change", { bubbles: true, cancelable: true }));
    await waitFor(() => tempUploads === 1);

    document.querySelector<HTMLButtonElement>("button[type='submit']")!.click();
    await waitFor(() => submitCount === 1);

    expect(promptAnalyze?.inputs.filter((input) => input.kind === "file_reference")).toHaveLength(1);
    expect(promptAnalyze?.inputs.some((input) => input.kind === "text" && input.source === "composer")).toBe(false);
    expect(promptAnalyze?.client_request_id).toBe(tempUploadRequestId);
    expect(document.documentElement.dataset.promptguardLastFailure).not.toBe("empty-prompt");
    shutdownPromptGuardContentScript();
  });

  it("keeps temp file refs after a blocked attachment send is canceled and resent", async () => {
    document.body.innerHTML = `
      <form id="composer">
        <textarea id="prompt-textarea" aria-label="Prompt"></textarea>
        ${attachmentChipMarkup(".pdf", "application/pdf", "8192", "file")}
        <input id="file-input" type="file" multiple />
        <button type="submit" data-testid="send-button">Send</button>
      </form>
    `;
    document.querySelector<HTMLTextAreaElement>("#prompt-textarea")!.value = "ㅇㅇ";
    let submitCount = 0;
    document.querySelector<HTMLFormElement>("#composer")!.addEventListener("submit", (event) => {
      event.preventDefault();
      submitCount += 1;
    });

    const promptAnalyzes: AnalyzeRequest[] = [];
    let tempUploadRequestId: string | undefined;
    vi.stubGlobal("chrome", {
      runtime: {
        id: "promptguard-test",
        sendMessage: vi.fn(async (message: { type: string; payload?: unknown }) => {
          if (message.type === "GET_CONFIG_REQUEST") {
            return DEFAULT_CONFIG;
          }
          if (message.type === "TEMP_FILE_UPLOAD_REQUEST") {
            const payload = message.payload as { fileKind: string; extension: string; mime: string; requestId: string };
            tempUploadRequestId = payload.requestId;
            return {
              file_ref: "fref_cancelcontentabcdefghijkl",
              temp_scope_id: "tscope_cancelcontentabcdefghijkl",
              file_kind: payload.fileKind,
              extension_hint: payload.extension,
              mime_hint: payload.mime,
              size_bucket: "tiny",
              expires_at: "2026-06-25T00:00:00Z"
            };
          }
          if (message.type === "PROMPT_ANALYZE_REQUEST") {
            const request = message.payload as AnalyzeRequest;
            promptAnalyzes.push(request);
            return {
              ...responseFor(request),
              action: "Block",
              allow_original_send: false,
              risk_score: 90,
              risk_level: "high"
            } satisfies AnalyzeResponse;
          }
          return {};
        })
      }
    });

    const { initializePromptGuardContentScript, shutdownPromptGuardContentScript } = await import("../../src/content/contentScript");
    await initializePromptGuardContentScript(document.body);

    const input = document.querySelector<HTMLInputElement>("#file-input")!;
    Object.defineProperty(input, "files", {
      value: fileListLike([pdfAttachment()]),
      configurable: true
    });
    input.dispatchEvent(new Event("change", { bubbles: true, cancelable: true }));
    await waitFor(() => tempUploadRequestId !== undefined);

    document.querySelector<HTMLButtonElement>("button[type='submit']")!.click();
    await waitFor(() => promptAnalyzes.length === 1);
    await waitFor(() => document.querySelector<HTMLButtonElement>("#promptguard-preflight-overlay button[data-promptguard-action='cancel']") !== null);
    clickOverlayAction("cancel");
    document.querySelector<HTMLButtonElement>("button[type='submit']")!.click();
    await waitFor(() => promptAnalyzes.length === 2);

    expect(submitCount).toBe(0);
    expect(promptAnalyzes.map((request) => request.client_request_id)).toEqual([tempUploadRequestId, tempUploadRequestId]);
    expect(promptAnalyzes.every((request) => request.inputs.some((input) => input.kind === "file_reference"))).toBe(true);
    shutdownPromptGuardContentScript();
  });

  it("waits for pending temp upload when send is clicked before file registration finishes", async () => {
    document.body.innerHTML = `
      <form id="composer">
        <textarea id="prompt-textarea" aria-label="Prompt"></textarea>
        ${attachmentChipMarkup(".txt", "text/plain", "4096", "file")}
        ${attachmentChipMarkup(".png", "image/png", "2048", "image")}
        ${attachmentChipMarkup(".pdf", "application/pdf", "8192", "file")}
        <input id="file-input" type="file" multiple />
        <button type="submit" data-testid="send-button">Send</button>
      </form>
    `;
    let submitCount = 0;
    document.querySelector<HTMLFormElement>("#composer")!.addEventListener("submit", (event) => {
      event.preventDefault();
      submitCount += 1;
    });

    let promptAnalyze: AnalyzeRequest | undefined;
    let resolveUpload: (() => void) | undefined;
    const uploadGate = new Promise<void>((resolve) => {
      resolveUpload = resolve;
    });
    vi.stubGlobal("chrome", {
      runtime: {
        id: "promptguard-test",
        sendMessage: vi.fn(async (message: { type: string; payload?: unknown }) => {
          if (message.type === "GET_CONFIG_REQUEST") {
            return DEFAULT_CONFIG;
          }
          if (message.type === "TEMP_FILE_UPLOAD_REQUEST") {
            const payload = message.payload as { fileKind: string; extension: string; mime: string };
            await uploadGate;
            return {
              file_ref: "fref_pendingabcdefghijklmnopqrstuvwxyz",
              temp_scope_id: "tscope_pendingabcdefghijklmnopqr",
              file_kind: payload.fileKind,
              extension_hint: payload.extension,
              mime_hint: payload.mime,
              size_bucket: "tiny",
              expires_at: "2026-06-25T00:00:00Z"
            };
          }
          if (message.type === "PROMPT_ANALYZE_REQUEST") {
            promptAnalyze = message.payload as AnalyzeRequest;
            return responseFor(promptAnalyze);
          }
          return {};
        })
      }
    });

    const { initializePromptGuardContentScript, shutdownPromptGuardContentScript } = await import("../../src/content/contentScript");
    await initializePromptGuardContentScript(document.body);

    const input = document.querySelector<HTMLInputElement>("#file-input")!;
    Object.defineProperty(input, "files", {
      value: fileListLike([pdfAttachment()]),
      configurable: true
    });
    input.dispatchEvent(new Event("change", { bubbles: true, cancelable: true }));
    document.querySelector<HTMLButtonElement>("button[type='submit']")!.click();

    await new Promise((resolve) => window.setTimeout(resolve, 20));
    expect(submitCount).toBe(0);
    expect(promptAnalyze).toBeUndefined();

    resolveUpload?.();
    await waitFor(() => submitCount === 1);

    expect(promptAnalyze?.inputs.filter((item) => item.kind === "file_reference")).toHaveLength(1);
    expect(document.documentElement.dataset.promptguardLastFailure).not.toBe("inspection-failed");
    shutdownPromptGuardContentScript();
  });
});

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

function attachmentChipMarkup(extension: string, mime: string, sizeBytes: string, kind: string): string {
  return `
    <div
      data-promptguard-attachment-chip
      data-promptguard-extension="${extension}"
      data-promptguard-mime="${mime}"
      data-promptguard-size-bytes="${sizeBytes}"
      data-promptguard-attachment-kind="${kind}"
    >
      fixture-attachment
    </div>
  `;
}

function responseFor(request: AnalyzeRequest): AnalyzeResponse {
  return {
    event_id: "evt_content_file_test",
    request_id: "req_content_file_test",
    action: "Allow",
    checked_at: "2026-06-09T00:00:00Z",
    risk_score: 1,
    risk_level: "low",
    user_message: "PromptGuard decision",
    allow_original_send: true,
    requires_user_confirmation: false,
    detections: [],
    input_results: request.inputs.map((input, index) => ({
      input_id: input.input_id,
      input_index: index,
      kind: input.kind,
      source: input.source,
      content_included: input.content_included,
      content_scanned: input.kind === "text" && input.content_included,
      decision_basis: "no_detection"
    })),
    content_unavailable_inputs: [],
    business_context_matches: [],
    client_request_id: request.client_request_id,
    filter_config_revision: DEFAULT_POLICY_VERSION
  };
}

function clickOverlayAction(action: string): void {
  document.querySelector<HTMLButtonElement>(`#promptguard-preflight-overlay button[data-promptguard-action='${action}']`)!.click();
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
