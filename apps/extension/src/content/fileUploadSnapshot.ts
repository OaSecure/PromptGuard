import { createClientRequestId } from "../shared/hashing";
import type { FilePolicyInput } from "../shared/filePolicy";

/** Identifies how the user tried to attach files. */
export type FileUploadMethod = "INPUT" | "DROP";

/** Describes one file attach attempt captured before the page handles it. */
export interface FileUploadAttempt {
  method: FileUploadMethod;
  target: EventTarget | null;
  files: File[];
}

/**
 * Holds transient file references for the current preflight operation.
 *
 * `policyInput` contains only metadata needed before reading. The original
 * filename stays inside the browser `File` object and is not copied into the
 * Analyze request.
 */
export interface FileUploadSnapshot {
  client_file_id: string;
  file: File;
  policyInput: FilePolicyInput;
}

/** Converts a browser `FileList` into an array that can be inspected safely. */
export function filesFromFileList(files: FileList | null | undefined): File[] {
  return files ? Array.from(files) : [];
}

/**
 * Creates per-file snapshots with generated client IDs.
 *
 * Generated IDs let later results refer to files without sending original
 * filenames across the Analyze boundary.
 */
export function createFileUploadSnapshots(files: File[]): FileUploadSnapshot[] {
  return files.map((file) => ({
    client_file_id: createClientRequestId("file"),
    file,
    policyInput: {
      name: file.name,
      size: file.size,
      type: file.type
    }
  }));
}
