import { createFileReferenceInput, createUnsupportedAttachmentInput } from "../shared/analyzeRequestBuilder";
import type { TempUploadResult } from "../background/tempFileUploadClient";
import { attachmentPolicy } from "../shared/configAccessors";
import type { AnalyzeFileKind } from "../shared/types";
import { createClientRequestId } from "../shared/hashing";
import { validateFilePolicy } from "../shared/filePolicy";
import type { AnalyzeInput, ExtensionConfigResponse, ExtensionContext, NormalizedError } from "../shared/types";
import { createFileUploadSnapshots, type FileUploadAttempt } from "./fileUploadSnapshot";
import { installFileUploadInterceptor, type FileUploadInterceptor } from "./fileUploadInterceptor";
import { createPreflightOverlay, type PreflightOverlay } from "./preflightOverlay";

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
  uploadFile?: (payload: { file: File; requestId: string; fileKind: AnalyzeFileKind; extension: string; mime: string }) => Promise<TempUploadResult | NormalizedError>;
  registerInputs?: (inputs: AnalyzeInput[]) => void;
  getUploadRequestId?: () => string;
  beginUpload?: () => void;
  endUpload?: () => void;
  overlay?: PreflightOverlay;
}

/** Owns the lifecycle of file upload preflight hooks and UI state. */
export interface FileUploadPreflightController {
  disconnect(): void;
}

/**
 * Starts file reference registration for input and drop attach attempts.
 *
 * The controller validates policy without reading file content, lets the page
 * attach normally, then creates opaque upload/temp references for the final
 * prompt-send inspection request.
 */
export function startFileUploadPreflightController(options: FileUploadPreflightControllerOptions): FileUploadPreflightController {
  const doc = options.document ?? document;
  const overlay = options.overlay ?? createPreflightOverlay(doc);
  const selectors = serviceSelectors(options.config);
  let currentAttemptId = 0;
  let analyzing = false;
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
    onFileAttempt: (attempt) => {
      void handleAttempt(attempt);
    }
  });

  async function handleAttempt(attempt: FileUploadAttempt): Promise<void> {
    if (analyzing) {
      overlay.show({ decision: "analyzing", message: "이미 파일 검사 중입니다.", actions: [] });
      return;
    }

    const snapshots = createFileUploadSnapshots(attempt.files);
    const policyDecisions = validateFilePolicy(
      snapshots.map((snapshot) => snapshot.policyInput),
      attachmentPolicy(options.config)
    );
    const rejected = policyDecisions.find((decision) => !decision.allowed && (decision.reason === "disabled" || decision.reason === "too_many_files" || decision.reason === "batch_too_large"));
    if (rejected) {
      options.registerInputs?.(buildMetadataOnlyInputs(snapshots, policyDecisions));
      return;
    }

    const attemptId = ++currentAttemptId;
    analyzing = true;
    options.beginUpload?.();

    try {
      const supportedFilesNeedingUpload = policyDecisions.some((decision) => decision.allowed);
      if (supportedFilesNeedingUpload && !options.uploadFile) {
        options.registerInputs?.(fallbackUnavailableInputs(snapshots, policyDecisions));
        return;
      }

      const requestId = options.getUploadRequestId?.() ?? requestIdForAttempt(attempt);
      const inputs: AnalyzeInput[] = buildMetadataOnlyInputs(snapshots, policyDecisions);
      for (const [index, snapshot] of snapshots.entries()) {
        const decision = policyDecisions[index]; if (!decision?.allowed || !options.uploadFile) continue;
        const fileKind = kindFor(snapshot.file.type, decision.extension);
        const uploaded = await options.uploadFile({ file: snapshot.file, requestId, fileKind, extension: decision.extension, mime: snapshot.file.type });
        if (!("file_ref" in uploaded)) {
          inputs.push(unavailableInput(snapshot, index, decision.extension));
          continue;
        }
        inputs.push(createFileReferenceInput({ fileRef: uploaded.file_ref, tempScopeId: uploaded.temp_scope_id, fileKind: uploaded.file_kind, extension: uploaded.extension_hint ?? decision.extension, mimeType: uploaded.mime_hint ?? snapshot.file.type, sizeBytes: snapshot.file.size, sizeBucket: uploaded.size_bucket }));
      }
      if (attemptId === currentAttemptId && inputs.length > 0) {
        options.registerInputs?.(inputs);
      }
    } catch {
      if (attemptId === currentAttemptId) {
        options.registerInputs?.(fallbackUnavailableInputs(snapshots, policyDecisions));
      }
    } finally {
      options.endUpload?.();
      if (attemptId === currentAttemptId) {
        analyzing = false;
      }
    }
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

function serviceSelectors(config: ExtensionConfigResponse): { file_input: string[]; drop_zone: string[] } {
  const serviceConfig = config.ai_service_configs.find((item) => item.service === "CHATGPT") ?? config.ai_service_configs[0];
  return {
    file_input: serviceConfig.selectors.file_input,
    drop_zone: serviceConfig.selectors.drop_zone
  };
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
    if (decision.reason === "excluded_extension" || decision.reason === "unsupported_extension" || decision.reason === "non_inspectable_mime") {
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

function fallbackUnavailableInputs(
  snapshots: Array<{ file: File }>,
  decisions: Array<{ allowed: boolean; extension: string; reason?: string }>
): AnalyzeInput[] {
  return snapshots.map((snapshot, index) => unavailableInput(snapshot, index, decisions[index]?.extension ?? ""));
}

function unavailableInput(snapshot: { file: File }, index: number, extension: string): AnalyzeInput {
  return createUnsupportedAttachmentInput({
    extension,
    mimeType: snapshot.file.type,
    sizeBytes: snapshot.file.size,
    attachmentIndex: index,
    reason: "unavailable"
  });
}
