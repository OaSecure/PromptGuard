import type { FilesAnalyzeRequest } from "../shared/types";
import type { FilePolicyDecision } from "../shared/filePolicy";
import type { FileUploadSnapshot } from "./fileUploadSnapshot";

export async function readAllowedTextFiles(
  snapshots: FileUploadSnapshot[],
  decisions: FilePolicyDecision[]
): Promise<FilesAnalyzeRequest["files"]> {
  const requestFiles: FilesAnalyzeRequest["files"] = [];

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
  if (content.length > 0 && controlCharacters / content.length > 0.05) {
    throw new Error("Selected file content is not text.");
  }

  return content;
}
