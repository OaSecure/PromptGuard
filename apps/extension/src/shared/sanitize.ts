const FORBIDDEN_KEYS = new Set([
  "raw_prompt",
  "file_content",
  "fileContent",
  "extracted_text",
  "extractedText",
  "detected_raw_value",
  "detectedRawValue",
  "filename",
  "fileName",
  "file_name",
  "original_filename",
  "originalFileName",
  "masked_prompt",
  "maskedPrompt",
  "content_text",
  "contentText",
  "text"
]);

/**
 * Redacts forbidden raw-value keys from diagnostic objects.
 *
 * This helper is for defensive diagnostics only. It does not authorize logging
 * raw prompt text, file content, original filenames, or detected raw values.
 */
export function sanitizeForDiagnostics(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeForDiagnostics(item));
  }
  if (typeof value !== "object" || value === null) {
    return value;
  }

  const result: Record<string, unknown> = {};
  for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
    if (FORBIDDEN_KEYS.has(key)) {
      result[key] = "[redacted]";
      continue;
    }
    result[key] = sanitizeForDiagnostics(nested);
  }
  return result;
}

/**
 * Detects whether a diagnostic object still contains forbidden raw-value keys.
 *
 * Tests use this to catch accidental expansion of logs, snapshots, or error
 * payloads into privacy-sensitive fields.
 */
export function containsForbiddenDiagnosticKey(value: unknown): boolean {
  if (Array.isArray(value)) {
    return value.some((item) => containsForbiddenDiagnosticKey(item));
  }
  if (typeof value !== "object" || value === null) {
    return false;
  }
  return Object.entries(value as Record<string, unknown>).some(
    ([key, nested]) => FORBIDDEN_KEYS.has(key) || containsForbiddenDiagnosticKey(nested)
  );
}
