import { DEFAULT_CONFIG, EXTENSION_VERSION } from "../shared/constants";
import { filterConfigRevision } from "../shared/configAccessors";
import { isExtensionConfigResponse } from "../shared/configValidation";
import type { AnalyzeRequest, ExtensionConfigResponse, ExtensionContext } from "../shared/types";
import { collectAttachmentChipInputs, resolveAttachmentChipScope } from "./attachmentChipCapture";
import { findBestInputCandidate } from "./domDetector";
import { watchInputArea } from "./mutationWatcher";
import {
  buildPromptAnalyzeRequest as buildPromptAnalyzeRequestFromInput,
  startPromptPreflightController,
  type PromptPreflightController
} from "./promptPreflightController";
import { startFileUploadPreflightController, type FileUploadPreflightController } from "./fileUploadPreflightController";
import {
  beginRegisteredAttachmentUpload,
  clearRegisteredAttachmentInputs,
  endRegisteredAttachmentUpload,
  getOrCreateRegisteredAttachmentRequestId,
  getRegisteredAttachmentInputs,
  getRegisteredAttachmentRequestId,
  hasPendingRegisteredAttachmentUploads,
  registerAttachmentInputs,
  waitForRegisteredAttachmentUploads
} from "./registeredAttachmentInputs";

let activeConfig: ExtensionConfigResponse = DEFAULT_CONFIG;
let watcher: ReturnType<typeof watchInputArea> | undefined;
let preflightController: PromptPreflightController | undefined;
let fileUploadController: FileUploadPreflightController | undefined;

function currentContext(): ExtensionContext {
  return {
    ai_service: "CHATGPT",
    ai_service_domain: window.location.hostname,
    page_url_origin: window.location.origin,
    extension_version: EXTENSION_VERSION,
    browser: "Chrome",
    locale: navigator.language || "en-US"
  };
}

function refreshInputMarker(): void {
  const config = activeConfig.ai_service_configs.find((item) => item.service === "CHATGPT");
  const candidate = findBestInputCandidate(document, { input: config?.selectors.input ?? DEFAULT_CONFIG.ai_service_configs[0].selectors.input });
  document.documentElement.dataset.promptguardInputDetected = candidate ? "true" : "false";
}

/**
 * Builds a prompt analysis request from the currently detected input.
 *
 * This test-facing helper mirrors the live controller request builder while
 * preserving the content-script privacy boundary: page context contains only
 * the origin and service metadata, not the full URL path or query string.
 */
export function buildPromptAnalyzeRequest(inputMethod: "CLICK" | "ENTER" | "UNKNOWN" = "UNKNOWN"): AnalyzeRequest | null {
  const config = activeConfig.ai_service_configs.find((item) => item.service === "CHATGPT");
  const candidate = findBestInputCandidate(document, { input: config?.selectors.input ?? DEFAULT_CONFIG.ai_service_configs[0].selectors.input });
  if (!candidate) {
    return null;
  }
  return buildPromptAnalyzeRequestFromInput(
    candidate.element,
    inputMethod,
    currentContext(),
    filterConfigRevision(activeConfig),
    undefined,
    undefined,
    [
      ...collectAttachmentChipInputs(resolveAttachmentChipScope(candidate.element, document), {
        attachment_chip: config?.selectors.attachment_chip ?? DEFAULT_CONFIG.ai_service_configs[0].selectors.attachment_chip
      }),
      ...getRegisteredAttachmentInputs()
    ]
  );
}

function installPreflight(root: HTMLElement): void {
  refreshInputMarker();
  // Config can reload after the first install; disconnect first so one page
  // action cannot be handled by two generations of hooks.
  watcher?.disconnect();
  watcher = watchInputArea(root, refreshInputMarker);
  preflightController?.disconnect();
  preflightController = startPromptPreflightController({
    config: activeConfig,
    getContext: currentContext,
    sendAnalyze: (payload: AnalyzeRequest) => chrome.runtime.sendMessage({ type: "PROMPT_ANALYZE_REQUEST", payload }),
    getRegisteredAttachmentInputs,
    getRegisteredAttachmentRequestId,
    hasPendingRegisteredAttachmentUploads,
    waitForRegisteredAttachmentUploads,
    clearRegisteredAttachmentInputs
  });
  fileUploadController?.disconnect();
  fileUploadController = startFileUploadPreflightController({
    config: activeConfig,
    getContext: currentContext,
    uploadFile: async ({ file, ...payload }) =>
      chrome.runtime.sendMessage({
        type: "TEMP_FILE_UPLOAD_REQUEST",
        payload: {
          ...payload,
          file_bytes_base64: await fileToBase64(file),
          size_bytes: file.size
        }
      }),
    registerInputs: registerAttachmentInputs,
    getUploadRequestId: getOrCreateRegisteredAttachmentRequestId,
    beginUpload: beginRegisteredAttachmentUpload,
    endUpload: endRegisteredAttachmentUpload
  });
}

async function fileToBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await readFileArrayBuffer(file));
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

async function readFileArrayBuffer(file: File): Promise<ArrayBuffer> {
  if (typeof file.arrayBuffer === "function") {
    return file.arrayBuffer();
  }
  return new Response(file).arrayBuffer();
}

async function loadConfig(): Promise<void> {
  try {
    const response = await chrome.runtime.sendMessage({ type: "GET_CONFIG_REQUEST" });
    if (isExtensionConfigResponse(response)) {
      activeConfig = response;
    }
  } catch {
    activeConfig = DEFAULT_CONFIG;
  }
}

/**
 * Starts DOM preflight protection for the current page.
 *
 * Hooks install once with the default config before the async config request
 * completes, then install again with the fetched config when it is valid.
 * This keeps early user sends covered even when the background worker or
 * config API is slow.
 */
export async function initializePromptGuardContentScript(root: HTMLElement = defaultContentRoot()): Promise<void> {
  installPreflight(root);
  await loadConfig();
  installPreflight(root);
}

function defaultContentRoot(): HTMLElement {
  return document.body ?? document.documentElement;
}

/**
 * Removes all PromptGuard DOM hooks from the current page.
 *
 * Tests and controlled reload paths use this to prove that watchers and
 * interceptors do not leak between installs.
 */
export function shutdownPromptGuardContentScript(): void {
  watcher?.disconnect();
  watcher = undefined;
  preflightController?.disconnect();
  preflightController = undefined;
  fileUploadController?.disconnect();
  fileUploadController = undefined;
  clearRegisteredAttachmentInputs();
}

if (typeof chrome !== "undefined" && chrome.runtime?.id) {
  void initializePromptGuardContentScript(defaultContentRoot());
}
