/**
 * Extracts a lowercase extension from a browser-provided filename.
 *
 * The value is used only for policy classification and request metadata; the
 * original filename must not be copied into Analyze requests or diagnostics.
 */
export function extensionFromName(fileName: string): string {
  const lastDot = fileName.lastIndexOf(".");
  if (lastDot < 0) {
    return "";
  }
  return fileName.slice(lastDot).toLowerCase();
}

/**
 * Classifies MIME types that are acceptable for the text-only MVP.
 *
 * Some source/config files use `application/*` MIME values even though they are
 * text, so the allowlist includes common text-oriented application types while
 * leaving binary-oriented types rejected.
 */
export function isLikelyTextMime(mimeType: string): boolean {
  const normalized = mimeType.toLowerCase().split(";")[0].trim();
  return (
    normalized.startsWith("text/") ||
    normalized === "application/json" ||
    normalized === "application/xml" ||
    normalized === "application/yaml" ||
    normalized === "application/x-yaml" ||
    normalized === "application/javascript" ||
    normalized === "application/ecmascript" ||
    normalized === "application/sql"
  );
}
