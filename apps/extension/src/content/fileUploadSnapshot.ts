import { createClientRequestId } from "../shared/hashing";
import type { FilePolicyInput } from "../shared/filePolicy";

export type FileUploadMethod = "INPUT" | "DROP";

export interface FileUploadAttempt {
  method: FileUploadMethod;
  target: EventTarget | null;
  files: File[];
}

export interface FileUploadSnapshot {
  client_file_id: string;
  file: File;
  policyInput: FilePolicyInput;
}

export function filesFromFileList(files: FileList | null | undefined): File[] {
  return files ? Array.from(files) : [];
}

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
