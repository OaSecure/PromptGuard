import type { AnalyzeInput } from "../shared/types";
import { createClientRequestId } from "../shared/hashing";

const registeredInputs: AnalyzeInput[] = [];
let registeredRequestId: string | undefined;
let pendingUploads = 0;
const uploadWaiters = new Set<() => void>();

/** Returns the Analyze request id that owns the current temporary file refs. */
export function getOrCreateRegisteredAttachmentRequestId(): string {
  registeredRequestId ??= createClientRequestId("crq");
  return registeredRequestId;
}

/** Returns the active temporary file request id, if attachments are registered. */
export function getRegisteredAttachmentRequestId(): string | undefined {
  return registeredInputs.length > 0 ? registeredRequestId : undefined;
}

/** Stores transient file_reference inputs created from live File/Blob handles. */
export function registerAttachmentInputs(inputs: AnalyzeInput[], requestId?: string): void {
  if (requestId && registeredRequestId !== requestId) {
    return;
  }
  registeredInputs.push(...inputs);
}

/** Returns a copy of currently registered attachment inputs for the send attempt. */
export function getRegisteredAttachmentInputs(): AnalyzeInput[] {
  return [...registeredInputs];
}

/** Clears transient attachment inputs after the native send path is replayed. */
export function clearRegisteredAttachmentInputs(): void {
  registeredInputs.length = 0;
  registeredRequestId = undefined;
}

/** Marks one native file attachment upload as in progress. */
export function beginRegisteredAttachmentUpload(): void {
  pendingUploads += 1;
}

/** Marks one native file attachment upload as finished and wakes send waiters. */
export function endRegisteredAttachmentUpload(): void {
  pendingUploads = Math.max(0, pendingUploads - 1);
  if (pendingUploads === 0) {
    for (const waiter of uploadWaiters) {
      waiter();
    }
    uploadWaiters.clear();
  }
}

/** Returns whether any file upload/temp handoff is still pending. */
export function hasPendingRegisteredAttachmentUploads(): boolean {
  return pendingUploads > 0;
}

/** Resolves after all current file upload/temp handoffs finish. */
export function waitForRegisteredAttachmentUploads(): Promise<void> {
  if (pendingUploads === 0) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    uploadWaiters.add(resolve);
  });
}
