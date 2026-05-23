import { DEFAULT_POLICY_VERSION, EXTENSION_VERSION } from "../shared/constants";
import { createClientRequestId } from "../shared/hashing";
import { validateFilePolicy } from "../shared/filePolicy";
import { isFilesAnalyzeResponse } from "../shared/responseValidation";
import type { ExtensionConfigResponse, ExtensionContext, FilesAnalyzeRequest, FilesAnalyzeResponse, NormalizedError } from "../shared/types";
import { createFileUploadSnapshots, type FileUploadAttempt } from "./fileUploadSnapshot";
import { installFileUploadInterceptor, replayFileUploadAttempt, type FileUploadInterceptor } from "./fileUploadInterceptor";
import { readAllowedTextFiles } from "./textFileReader";
import { createPreflightOverlay, type PreflightOverlay } from "./preflightOverlay";

/** Sends one text-file inspection request through the background boundary. */
export type FilesAnalyzeSender = (request: FilesAnalyzeRequest) => Promise<FilesAnalyzeResponse | NormalizedError>;

/**
 * Configures the text-file upload preflight controller.
 *
 * `getContext` runs at attach time so each file inspection request carries the
 * current service domain and extension version without persisting page state.
 */
export interface FileUploadPreflightControllerOptions {
  document?: Document;
  config: ExtensionConfigResponse;
  getContext: () => ExtensionContext;
  sendAnalyze: FilesAnalyzeSender;
  overlay?: PreflightOverlay;
}

/** Owns the lifecycle of file upload preflight hooks and UI state. */
export interface FileUploadPreflightController {
  disconnect(): void;
}

/**
 * Starts text-file inspection for input and drop attach attempts.
 *
 * The controller validates policy before reading content, reads only supported
 * text files in memory, and replays the attach attempt only after a validated
 * Allow or confirmed Warn decision.
 */
export function startFileUploadPreflightController(options: FileUploadPreflightControllerOptions): FileUploadPreflightController {
  const doc = options.document ?? document;
  const overlay = options.overlay ?? createPreflightOverlay(doc);
  const selectors = serviceSelectors(options.config);
  let currentAttemptId = 0;
  let analyzing = false;
  let replaying = false;

  const interceptor: FileUploadInterceptor = installFileUploadInterceptor({
    document: doc,
    fileInputSelectors: selectors.file_input,
    dropZoneSelectors: selectors.drop_zone,
    shouldBypass: () => replaying,
    onFileAttempt: (attempt) => {
      void handleAttempt(attempt);
    }
  });

  async function handleAttempt(attempt: FileUploadAttempt): Promise<void> {
    if (analyzing) {
      overlay.show({ decision: "analyzing", message: "File inspection is already running.", actions: [] });
      return;
    }

    const snapshots = createFileUploadSnapshots(attempt.files);
    const policyDecisions = validateFilePolicy(
      snapshots.map((snapshot) => snapshot.policyInput),
      options.config.file_upload
    );
    const rejected = policyDecisions.find((decision) => !decision.allowed);
    if (rejected) {
      showBlocked(policyMessage(rejected.reason));
      return;
    }

    const attemptId = ++currentAttemptId;
    analyzing = true;
    overlay.show({ decision: "analyzing", message: "Inspecting attached text files.", actions: [] });

    try {
      const files = await readAllowedTextFiles(snapshots, policyDecisions);
      const response = await withTimeout(options.sendAnalyze(buildFilesAnalyzeRequest(files, options.getContext(), options.config.policy_version)), options.config.timeout_ms);
      if (attemptId !== currentAttemptId) {
        return;
      }
      if (!isFilesAnalyzeResponse(response)) {
        showFailClosed("File inspection failed. Files were not attached.", () => void handleAttempt(attempt));
        return;
      }
      handleDecision(response, attempt);
    } catch {
      if (attemptId === currentAttemptId) {
        showFailClosed("File inspection timed out or could not read the selected text files.", () => void handleAttempt(attempt));
      }
    } finally {
      if (attemptId === currentAttemptId) {
        analyzing = false;
      }
    }
  }

  function handleDecision(response: FilesAnalyzeResponse, attempt: FileUploadAttempt): void {
    switch (response.decision.action) {
      case "Allow":
        // A false authorization flag overrides the Allow action because the
        // native file attach is the irreversible page action.
        if (response.decision.allow_original_upload === false) {
          showFailClosed("File inspection did not authorize attaching the original files.", () => void handleAttempt(attempt));
          return;
        }
        replayOrFallback(attempt);
        return;
      case "Warn":
        overlay.show({
          decision: "warn",
          message: "PromptGuard found attached file content that may need review.",
          actions: [
            { label: "Continue", variant: "primary", onClick: () => replayOrFallback(attempt) },
            { label: "Cancel", variant: "secondary", onClick: overlay.hide }
          ]
        });
        return;
      case "Block":
      case "Mask":
        showBlocked("PromptGuard blocked these attached files based on policy.");
        return;
    }
  }

  function replayOrFallback(attempt: FileUploadAttempt): void {
    overlay.hide();
    // Keep the bypass window as small as possible so only this approved replay
    // skips interception.
    replaying = true;
    const replayed = replayFileUploadAttempt(attempt);
    replaying = false;
    if (!replayed) {
      overlay.show({
        decision: "error",
        message: "File inspection passed. Please attach the files again because this page did not allow automatic reattach.",
        actions: [{ label: "Cancel", variant: "secondary", onClick: overlay.hide }]
      });
    }
  }

  function showBlocked(message: string): void {
    overlay.show({
      decision: "block",
      message,
      actions: [{ label: "Cancel", variant: "danger", onClick: overlay.hide }]
    });
  }

  function showFailClosed(message: string, retry: () => void): void {
    overlay.show({
      decision: "error",
      message,
      actions: [
        { label: "Retry", variant: "secondary", onClick: retry },
        { label: "Cancel", variant: "danger", onClick: overlay.hide }
      ]
    });
  }

  return {
    disconnect() {
      currentAttemptId += 1;
      interceptor.disconnect();
      overlay.destroy();
    }
  };
}

/**
 * Builds a files Analyze request from already-read text file entries.
 *
 * Original filenames are intentionally absent; file results are correlated
 * through generated client IDs and metadata that is safe to send.
 */
export function buildFilesAnalyzeRequest(
  files: FilesAnalyzeRequest["files"],
  context: ExtensionContext,
  policyVersion = DEFAULT_POLICY_VERSION
): FilesAnalyzeRequest {
  return {
    files,
    context: {
      ...context,
      extension_version: context.extension_version || EXTENSION_VERSION
    },
    policy: {
      version: policyVersion || DEFAULT_POLICY_VERSION
    },
    client_request_id: createClientRequestId("frq")
  };
}

function serviceSelectors(config: ExtensionConfigResponse): { file_input: string[]; drop_zone: string[] } {
  const serviceConfig = config.ai_service_configs.find((item) => item.service === "CHATGPT") ?? config.ai_service_configs[0];
  return {
    file_input: serviceConfig.selectors.file_input,
    drop_zone: serviceConfig.selectors.drop_zone
  };
}

function policyMessage(reason: string | undefined): string {
  switch (reason) {
    case "too_many_files":
      return "Too many files selected for inspection.";
    case "file_too_large":
    case "batch_too_large":
      return "Selected files exceed the configured inspection size limit.";
    case "excluded_extension":
    case "unsupported_extension":
    case "non_text_mime":
      return "Only supported text-based files can be inspected in this MVP.";
    case "disabled":
      return "File inspection is disabled by policy.";
    default:
      return "Selected files could not be inspected.";
  }
}

async function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  let timeoutId: number | undefined;
  const timeout = new Promise<never>((_resolve, reject) => {
    timeoutId = window.setTimeout(() => reject(new Error("PromptGuard file inspection timeout.")), timeoutMs);
  });

  try {
    return await Promise.race([promise, timeout]);
  } finally {
    if (timeoutId !== undefined) {
      window.clearTimeout(timeoutId);
    }
  }
}
