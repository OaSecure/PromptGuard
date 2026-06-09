import type { FilePolicyDecision } from "../shared/filePolicy";
import type { FileUploadSnapshot } from "./fileUploadSnapshot";

/** Safe transient text-file payload returned after in-memory reads. */
export interface ReadableTextFile {
  client_file_id: string;
  extension: string;
  mime_type: string;
  size_bytes: number;
  content_text: string;
}

/**
 * Reads policy-approved files into Analyze request entries.
 *
 * The reader is intentionally after file policy validation so unsupported
 * files are rejected before their contents are touched. Returned `content_text`
 * values are transient request payloads and must not be persisted or logged.
 */
export async function readAllowedTextFiles(
  snapshots: FileUploadSnapshot[],
  decisions: FilePolicyDecision[]
): Promise<ReadableTextFile[]> {
  const requestFiles: ReadableTextFile[] = [];

  for (const [index, snapshot] of snapshots.entries()) {
    const decision = decisions[index];
    if (!decision?.allowed) {
      continue;
    }

    requestFiles.push({
      client_file_id: snapshot.client_file_id,
      extension: decision.extension,
      mime_type: snapshot.file.type || "text/plain",
      size_bytes: snapshot.file.size,
      content_text: assertLikelyText(await readFileText(snapshot.file))
    });
  }

  return requestFiles;
}

function readFileText(file: File): Promise<string> {
  if (typeof file.text === "function") {
    return file.text();
  }

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result ?? "")), { once: true });
    reader.addEventListener("error", () => reject(reader.error ?? new Error("Unable to read selected file.")), { once: true });
    reader.readAsText(file);
  });
}

function assertLikelyText(content: string): string {
  if (content.includes("\u0000")) {
    throw new Error("Selected file content is not text.");
  }

  const controlCharacters = content.match(/[\u0001-\u0008\u000B\u000C\u000E-\u001F]/g)?.length ?? 0;
  // Some binary files decode into strings without NUL bytes. A control-heavy
  // result is treated as unreadable for the text-only MVP.
  if (content.length > 0 && controlCharacters / content.length > 0.05) {
    throw new Error("Selected file content is not text.");
  }

  return content;
}
