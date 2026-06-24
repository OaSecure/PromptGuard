import { createAnalyzeRequest, createFileReferenceInput, createUnsupportedAttachmentInput } from "../shared/analyzeRequestBuilder";
import type { TempUploadResult } from "../background/tempFileUploadClient";
import { analyzeTimeoutMs, attachmentPolicy, filterConfigRevision } from "../shared/configAccessors";
import type { AnalyzeFileKind } from "../shared/types";
import { createClientRequestId } from "../shared/hashing";
import { validateFilePolicy } from "../shared/filePolicy";
import { isAnalyzeResponse } from "../shared/responseValidation";
import type { AnalyzeInput, AnalyzeRequest, AnalyzeResponse, ExtensionConfigResponse, ExtensionContext, NormalizedError } from "../shared/types";
import { createFileUploadSnapshots, type FileUploadAttempt } from "./fileUploadSnapshot";
import { installFileUploadInterceptor, replayFileUploadAttempt, type FileUploadInterceptor } from "./fileUploadInterceptor";
import { createPreflightOverlay, type PreflightOverlay } from "./preflightOverlay";

/** Sends one attachment inspection request through the background boundary. */
export type FilesAnalyzeSender = (request: AnalyzeRequest) => Promise<AnalyzeResponse | NormalizedError>;

/**
 * Configures the file upload preflight controller.
 *
 * `getContext` runs at attach time so each file inspection request carries the
 * current service domain and extension version without persisting page state.
 */
export interface FileUploadPreflightControllerOptions {
  document?: Document;
  config: ExtensionConfigResponse;
  getContext: () => ExtensionContext;
  sendAnalyze: FilesAnalyzeSender;
  uploadFile?: (payload: { file: File; requestId: string; fileKind: AnalyzeFileKind; extension: string; mime: string }) => Promise<TempUploadResult | NormalizedError>;
  overlay?: PreflightOverlay;
}

/** Owns the lifecycle of file upload preflight hooks and UI state. */
export interface FileUploadPreflightController {
  disconnect(): void;
}

/**
 * Starts file upload preflight for input and drop attach attempts.
 *
 * The controller validates policy without reading file content, then routes
 * supported file handles through upload/temp file_ref inspection.
 */
export function startFileUploadPreflightController(options: FileUploadPreflightControllerOptions): FileUploadPreflightController {
  const doc = options.document ?? document;
  const overlay = options.overlay ?? createPreflightOverlay(doc);
  const selectors = serviceSelectors(options.config);
  let currentAttemptId = 0;
  let analyzing = false;
  let replaying = false;
  const requestIds = new WeakMap<FileUploadAttempt, string>();
  const requestIdForAttempt = (attempt: FileUploadAttempt): string => {
    const existing = requestIds.get(attempt);
    if (existing) {
      return existing;
    }
    const created = createClientRequestId("frq");
    requestIds.set(attempt, created);
    return created;
  };

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
      attachmentPolicy(options.config)
    );
    const rejected = policyDecisions.find((decision) => !decision.allowed && (decision.reason === "disabled" || decision.reason === "too_many_files" || decision.reason === "batch_too_large"));
    if (rejected) {
      showBlocked(policyMessage(rejected.reason));
      return;
    }

    const attemptId = ++currentAttemptId;
    analyzing = true;
    overlay.show({ decision: "analyzing", message: "Inspecting attached files.", actions: [] });

    try {
      const supportedFilesNeedingUpload = policyDecisions.some((decision) => decision.allowed);
      if (supportedFilesNeedingUpload && !options.uploadFile) {
        showFailClosed("File inspection requires temporary file reference support. Files were not attached.", () => void handleAttempt(attempt));
        return;
      }

      const requestId = requestIdForAttempt(attempt);
      const inputs: AnalyzeInput[] = buildMetadataOnlyInputs(snapshots, policyDecisions);
      for (const [index, snapshot] of snapshots.entries()) {
        const decision = policyDecisions[index]; if (!decision?.allowed || !options.uploadFile) continue;
        const fileKind = kindFor(snapshot.file.type, decision.extension);
        const uploaded = await options.uploadFile({ file: snapshot.file, requestId, fileKind, extension: decision.extension, mime: snapshot.file.type });
        if (!("file_ref" in uploaded)) throw new Error("upload failed");
        inputs.push(createFileReferenceInput({ fileRef: uploaded.file_ref, tempScopeId: uploaded.temp_scope_id, fileKind: uploaded.file_kind, extension: uploaded.extension_hint ?? decision.extension, mimeType: uploaded.mime_hint ?? snapshot.file.type, sizeBytes: snapshot.file.size, sizeBucket: uploaded.size_bucket }));
      }
      if (inputs.length === 0) {
        showFailClosed("Selected files could not be inspected safely. Files were not attached.", () => void handleAttempt(attempt));
        return;
      }
      const response = await withTimeout(
        options.sendAnalyze(buildFilesAnalyzeRequest(inputs, options.getContext(), filterConfigRevision(options.config), requestId)),
        analyzeTimeoutMs(options.config)
      );
      if (attemptId !== currentAttemptId) {
        return;
      }
      if (!isAnalyzeResponse(response)) {
        showFailClosed("File inspection failed. Files were not attached.", () => void handleAttempt(attempt));
        return;
      }
      handleDecision(response, attempt);
    } catch {
      if (attemptId === currentAttemptId) {
        showFailClosed("File inspection timed out or could not inspect the selected files.", () => void handleAttempt(attempt));
      }
    } finally {
      if (attemptId === currentAttemptId) {
        analyzing = false;
      }
    }
  }

  function handleDecision(response: AnalyzeResponse, attempt: FileUploadAttempt): void {
    switch (response.action) {
      case "Allow":
        if (response.allow_original_send === false) {
          showFailClosed("File inspection did not authorize attaching the original files.", () => void handleAttempt(attempt));
          return;
        }
        replayOrFallback(attempt);
        return;
      case "Warn":
        overlay.show({
          decision: "warn",
          message: "PromptGuard found attached files that may need review.",
          actions: [
            {
              label: "Continue",
              variant: "primary",
              onClick: () => {
                if (response.allow_original_send !== true) {
                  showFailClosed("File inspection did not authorize attaching the original files.", () => void handleAttempt(attempt));
                  return;
                }
                replayOrFallback(attempt);
              }
            },
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

function kindFor(mime: string, extension: string): AnalyzeFileKind {
  if (mime.startsWith("image/")) return "image"; if (extension === ".pdf") return "pdf";
  if ([".docx"].includes(extension)) return "office_document"; if ([".xlsx", ".csv"].includes(extension)) return "spreadsheet";
  if ([".pptx"].includes(extension)) return "slide"; if ([".py", ".js", ".ts", ".sql"].includes(extension)) return "code"; return "plain_text";
}

/**
 * Builds a files Analyze request from contract-safe attachment inputs.
 *
 * Original filenames are intentionally absent; file results are correlated
 * through generated client IDs and metadata that is safe to send.
 */
export function buildFilesAnalyzeRequest(
  inputs: AnalyzeInput[],
  context: ExtensionContext,
  policyVersion: string,
  clientRequestId?: string
): AnalyzeRequest {
  return createAnalyzeRequest(
    {
      ...context,
      extension_version: context.extension_version || "0.4.0"
    },
    policyVersion,
    inputs,
    clientRequestId
  );
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

function buildMetadataOnlyInputs(
  snapshots: Array<{ file: File }>,
  decisions: Array<{ allowed: boolean; extension: string; reason?: string }>
): AnalyzeInput[] {
  return snapshots.flatMap((snapshot, index) => {
    const decision = decisions[index];
    if (!decision || decision.allowed) {
      return [];
    }
    if (decision.reason === "file_too_large") {
      return [
        createUnsupportedAttachmentInput({
          extension: decision.extension,
          mimeType: snapshot.file.type,
          sizeBytes: snapshot.file.size,
          attachmentIndex: index,
          reason: "oversized"
        })
      ];
    }
    if (decision.reason === "excluded_extension" || decision.reason === "unsupported_extension" || decision.reason === "non_text_mime") {
      return [
        createUnsupportedAttachmentInput({
          extension: decision.extension,
          mimeType: snapshot.file.type,
          sizeBytes: snapshot.file.size,
          attachmentIndex: index
        })
      ];
    }
    return [];
  });
}
