import { DEFAULT_CONFIG, EXTENSION_VERSION } from "../shared/constants";
import { isExtensionConfigResponse } from "../shared/configValidation";
import type { AnalyzeRequest, ExtensionConfigResponse, ExtensionContext } from "../shared/types";
import { findBestInputCandidate } from "./domDetector";
import { watchInputArea } from "./mutationWatcher";
import {
  buildPromptAnalyzeRequest as buildPromptAnalyzeRequestFromInput,
  startPromptPreflightController,
  type PromptPreflightController
} from "./promptPreflightController";
import { startFileUploadPreflightController, type FileUploadPreflightController } from "./fileUploadPreflightController";

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

export function buildPromptAnalyzeRequest(inputMethod: "CLICK" | "ENTER" | "UNKNOWN" = "UNKNOWN"): AnalyzeRequest | null {
  const config = activeConfig.ai_service_configs.find((item) => item.service === "CHATGPT");
  const candidate = findBestInputCandidate(document, { input: config?.selectors.input ?? DEFAULT_CONFIG.ai_service_configs[0].selectors.input });
  if (!candidate) {
    return null;
  }
  return buildPromptAnalyzeRequestFromInput(candidate.element, inputMethod, currentContext(), activeConfig.policy_version);
}

function installPreflight(root: HTMLElement): void {
  refreshInputMarker();
  watcher?.disconnect();
  watcher = watchInputArea(root, refreshInputMarker);
  preflightController?.disconnect();
  preflightController = startPromptPreflightController({
    config: activeConfig,
    getContext: currentContext,
    sendAnalyze: (payload: AnalyzeRequest) => chrome.runtime.sendMessage({ type: "PROMPT_ANALYZE_REQUEST", payload })
  });
  fileUploadController?.disconnect();
  fileUploadController = startFileUploadPreflightController({
    config: activeConfig,
    getContext: currentContext,
    sendAnalyze: (payload) => chrome.runtime.sendMessage({ type: "FILES_ANALYZE_REQUEST", payload })
  });
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

export async function initializePromptGuardContentScript(root: HTMLElement = defaultContentRoot()): Promise<void> {
  installPreflight(root);
  await loadConfig();
  installPreflight(root);
}

function defaultContentRoot(): HTMLElement {
  return document.body ?? document.documentElement;
}

export function shutdownPromptGuardContentScript(): void {
  watcher?.disconnect();
  watcher = undefined;
  preflightController?.disconnect();
  preflightController = undefined;
  fileUploadController?.disconnect();
  fileUploadController = undefined;
}

if (typeof chrome !== "undefined" && chrome.runtime?.id) {
  void initializePromptGuardContentScript(defaultContentRoot());
}
