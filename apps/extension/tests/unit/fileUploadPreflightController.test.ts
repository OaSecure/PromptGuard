import { describe, expect, it } from "vitest";
import { DEFAULT_CONFIG } from "../../src/shared/constants";
import { startFileUploadPreflightController } from "../../src/content/fileUploadPreflightController";
import type { AnalyzeInput, ExtensionContext } from "../../src/shared/types";
import { csvAttachment, pdfAttachment, pngAttachment, textAttachment } from "../fixtures/attachmentFixtures";

const context: ExtensionContext = {
  ai_service: "CHATGPT",
  ai_service_domain: "chatgpt.com",
  page_url_origin: "https://chatgpt.com",
  extension_version: "0.4.0",
  browser: "Chrome",
  locale: "ko-KR"
};

describe("file upload preflight controller", () => {
  it("lets native file input attachment proceed while registering a temp file_ref for send-time inspection", async () => {
    const page = setupFileInput([pngAttachment()]);
    const registered: AnalyzeInput[][] = [];
    let uploadCalls = 0;
    const controller = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      registerInputs: (inputs) => registered.push(inputs),
      uploadFile: async ({ fileKind, extension, mime }) => {
        uploadCalls += 1;
        return {
          file_ref: "fref_abcdefghijklmnopqrstuvwxyz123456",
          temp_scope_id: "tscope_abcdefghijklmnopqrstuvwxyz123456",
          file_kind: fileKind,
          extension_hint: extension,
          mime_hint: mime,
          size_bucket: "tiny",
          expires_at: "2026-06-25T00:00:00Z"
        };
      }
    });

    const event = dispatchChange(page.input);
    await waitFor(() => uploadCalls === 1);

    expect(event.defaultPrevented).toBe(false);
    expect(page.uploads()).toBe(1);
    expect(registered[0][0]).toMatchObject({
      kind: "file_reference",
      source: "attached_file",
      file_kind: "image",
      extension: "png",
      mime: "image/png",
      content_included: false
    });
    expect(JSON.stringify(registered)).not.toContain("screenshot.png");
    expect(overlayDecision()).toBeUndefined();
    controller.disconnect();
  });

  it("lets native drop attachment proceed while registering file_ref inputs", async () => {
    document.body.innerHTML = `<div data-testid="drop-zone"></div>`;
    const dropZone = document.querySelector<HTMLElement>("[data-testid='drop-zone']")!;
    const registered: AnalyzeInput[][] = [];
    let uploadCalls = 0;
    const controller = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      registerInputs: (inputs) => registered.push(inputs),
      uploadFile: async ({ fileKind, extension, mime }) => {
        uploadCalls += 1;
        return {
          file_ref: "fref_abcdefghijklmnopqrstuvwxyz123456",
          temp_scope_id: "tscope_abcdefghijklmnopqrstuvwxyz123456",
          file_kind: fileKind,
          extension_hint: extension,
          mime_hint: mime,
          size_bucket: "tiny",
          expires_at: "2026-06-25T00:00:00Z"
        };
      }
    });

    const nonFileDrop = dropEvent([]);
    dropZone.dispatchEvent(nonFileDrop);
    expect(nonFileDrop.defaultPrevented).toBe(false);

    const fileDrop = dropEvent([pngAttachment("capture.png")]);
    dropZone.dispatchEvent(fileDrop);
    await waitFor(() => uploadCalls === 1);

    expect(fileDrop.defaultPrevented).toBe(false);
    expect(registered[0][0]).toMatchObject({
      kind: "file_reference",
      source: "attached_file",
      file_kind: "image",
      extension: "png",
      mime: "image/png"
    });
    expect(overlayDecision()).toBeUndefined();
    controller.disconnect();
  });

  it("registers unsupported attachment metadata without blocking native attachment", async () => {
    const page = setupFileInput([new File([new Uint8Array([0x50, 0x4b, 0x03, 0x04]).buffer], "archive.zip", { type: "application/zip" })]);
    const registered: AnalyzeInput[][] = [];
    const controller = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      registerInputs: (inputs) => registered.push(inputs)
    });

    const event = dispatchChange(page.input);
    await waitFor(() => registered.length === 1);

    expect(event.defaultPrevented).toBe(false);
    expect(page.uploads()).toBe(1);
    expect(registered[0][0]).toMatchObject({
      kind: "unsupported_attachment",
      source: "attachment_chip",
      content_included: false,
      content_unavailable_reason: "unsupported"
    });
    expect(JSON.stringify(registered)).not.toContain("archive.zip");
    expect(overlayDecision()).toBeUndefined();
    controller.disconnect();
  });

  it("does not register stale unavailable metadata when temp upload fails", async () => {
    const page = setupFileInput([textAttachment()]);
    const registered: AnalyzeInput[][] = [];
    const controller = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      registerInputs: (inputs) => registered.push(inputs),
      uploadFile: async () => ({ code: "NETWORK_ERROR", message: "upload failed" })
    });

    const event = dispatchChange(page.input);
    await waitFor(() => page.uploads() === 1);

    expect(event.defaultPrevented).toBe(false);
    expect(page.uploads()).toBe(1);
    expect(registered).toEqual([]);
    expect(overlayDecision()).toBeUndefined();
    controller.disconnect();
  });

  it("registers real PDF and CSV attachments as server-side file_reference inputs", async () => {
    const page = setupFileInput([pdfAttachment(), csvAttachment()]);
    const registered: AnalyzeInput[][] = [];
    const controller = startFileUploadPreflightController({
      config: DEFAULT_CONFIG,
      getContext: () => context,
      registerInputs: (inputs) => registered.push(inputs),
      uploadFile: async ({ fileKind, extension, mime }) => ({
        file_ref: "fref_pdfabcdefghijklmnopqrstuvwxyz123",
        temp_scope_id: "tscope_pdfabcdefghijklmnopqrstuvwxyz123",
        file_kind: fileKind,
        extension_hint: extension,
        mime_hint: mime,
        size_bucket: "tiny",
        expires_at: "2026-06-25T00:00:00Z"
      })
    });

    const event = dispatchChange(page.input);
    await waitFor(() => registered.length === 1);

    expect(event.defaultPrevented).toBe(false);
    expect(page.uploads()).toBe(1);
    expect(registered[0]).toHaveLength(2);
    expect(registered[0][0]).toMatchObject({
      kind: "file_reference",
      source: "attached_file",
      file_kind: "pdf",
      extension: "pdf",
      mime: "application/pdf",
      content_included: false
    });
    expect(registered[0][1]).toMatchObject({
      kind: "file_reference",
      source: "attached_file",
      file_kind: "spreadsheet",
      extension: "csv",
      mime: "text/csv",
      content_included: false
    });
    expect(JSON.stringify(registered)).not.toContain("context-risk-business-brief.pdf");
    expect(JSON.stringify(registered)).not.toContain("bulk-customer-pii.csv");
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

function dispatchChange(input: HTMLInputElement): Event {
  const event = new Event("change", { bubbles: true, cancelable: true });
  input.dispatchEvent(event);
  return event;
}

function dropEvent(files: File[]): DragEvent {
  const event = new Event("drop", { bubbles: true, cancelable: true }) as DragEvent;
  Object.defineProperty(event, "dataTransfer", {
    value: { files: fileListLike(files) },
    configurable: true
  });
  return event;
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
