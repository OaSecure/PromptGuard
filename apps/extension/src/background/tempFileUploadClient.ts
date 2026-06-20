import { getAuthState } from "./authStore";
import { getSettings } from "./configStore";
import type { AnalyzeFileKind, AnalyzeSizeBucket, NormalizedError } from "../shared/types";

/** Safe metadata returned after an encrypted temporary upload. */
export interface TempUploadResult { file_ref: string; file_kind: AnalyzeFileKind; mime_hint?: string; extension_hint?: string; size_bucket: AnalyzeSizeBucket; expires_at: string }

/** Uploads a file to the authenticated temporary-file boundary. */
export async function uploadTempFile(payload: { file: File; requestId: string; fileKind: AnalyzeFileKind; extension: string; mime: string }): Promise<TempUploadResult | NormalizedError> {
  const settings = await getSettings(); const auth = await getAuthState(); const form = new FormData();
  form.append("file", new Blob([payload.file], { type: payload.file.type }), "upload.bin");
  form.append("request_id", payload.requestId); form.append("file_kind", payload.fileKind);
  form.append("extension_hint", payload.extension.replace(/^\./, "")); form.append("mime_hint", payload.mime || "application/octet-stream");
  try {
    const response = await fetch(`${settings.apiBaseUrl.replace(/\/+$/, "")}/files/temp`, { method: "POST", headers: auth.accessToken ? { Authorization: `Bearer ${auth.accessToken}` } : {}, body: form });
    if (!response.ok) return { code: response.status === 401 ? "UNAUTHORIZED" : "VALIDATION_ERROR", message: "Temporary upload failed." };
    const value = await response.json(); return isResult(value) ? value : { code: "VALIDATION_ERROR", message: "Temporary upload response was invalid." };
  } catch { return { code: "NETWORK_ERROR", message: "Temporary upload failed." }; }
}
function isResult(value: any): value is TempUploadResult { return value && /^fref_[A-Za-z0-9_-]{32,}$/.test(value.file_ref) && typeof value.expires_at === "string"; }
