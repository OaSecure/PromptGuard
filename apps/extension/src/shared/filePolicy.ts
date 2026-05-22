import type { FileUploadPolicy } from "./types";
import { extensionFromName, isLikelyTextMime } from "./fileTypes";

/** File metadata used for policy checks before content is read. */
export interface FilePolicyInput {
  name: string;
  size: number;
  type: string;
}

/** Policy decision for one selected or dropped file. */
export interface FilePolicyDecision {
  allowed: boolean;
  extension: string;
  reason?: "disabled" | "too_many_files" | "file_too_large" | "batch_too_large" | "excluded_extension" | "unsupported_extension" | "non_text_mime";
}

/**
 * Decides which files are safe to read for the text-only MVP.
 *
 * The policy check runs before `File.text()` so unsupported files, oversized
 * batches, and non-text MIME types are rejected without touching file content.
 */
export function validateFilePolicy(files: FilePolicyInput[], policy: FileUploadPolicy): FilePolicyDecision[] {
  if (!policy.enabled) {
    return files.map((file) => ({ allowed: false, extension: extensionFromName(file.name), reason: "disabled" }));
  }

  const totalSize = files.reduce((total, file) => total + file.size, 0);
  const tooMany = files.length > policy.max_file_count;
  const batchTooLarge = totalSize > policy.max_total_size_bytes;
  const allowedExtensions = new Set(policy.allowed_extensions.map(normalizeExtension));
  const excludedExtensions = new Set(policy.excluded_extensions.map(normalizeExtension));

  return files.map((file) => {
    const extension = extensionFromName(file.name);
    if (tooMany) {
      return { allowed: false, extension, reason: "too_many_files" };
    }
    if (batchTooLarge) {
      return { allowed: false, extension, reason: "batch_too_large" };
    }
    if (file.size > policy.max_file_size_bytes) {
      return { allowed: false, extension, reason: "file_too_large" };
    }
    if (excludedExtensions.has(extension)) {
      return { allowed: false, extension, reason: "excluded_extension" };
    }
    if (!allowedExtensions.has(extension)) {
      return { allowed: false, extension, reason: "unsupported_extension" };
    }
    if (file.type && !isLikelyTextMime(file.type)) {
      return { allowed: false, extension, reason: "non_text_mime" };
    }
    return { allowed: true, extension };
  });
}

function normalizeExtension(extension: string): string {
  return extension.toLowerCase();
}
