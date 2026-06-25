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
 * Classifies MIME types that the attachment inspection flow can send to the
 * server parser/OCR boundary.
 */
export function isInspectableMime(mimeType: string): boolean {
  const normalized = mimeType.toLowerCase().split(";")[0].trim();
  return (
    normalized.startsWith("text/") ||
    normalized.startsWith("image/") ||
    normalized === "application/json" ||
    normalized === "application/xml" ||
    normalized === "application/yaml" ||
    normalized === "application/x-yaml" ||
    normalized === "application/javascript" ||
    normalized === "application/ecmascript" ||
    normalized === "application/sql" ||
    normalized === "application/pdf" ||
    normalized === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    normalized === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" ||
    normalized === "application/vnd.openxmlformats-officedocument.presentationml.presentation"
  );
}
