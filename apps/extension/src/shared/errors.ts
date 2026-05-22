import type { NormalizedError } from "./types";

export function normalizeError(error: unknown): NormalizedError {
  if (isNormalizedError(error)) {
    return error;
  }
  if (error instanceof Error && error.name === "AbortError") {
    return { code: "TIMEOUT", message: "Inspection timed out and the action is held." };
  }
  if (error instanceof TypeError) {
    return { code: "NETWORK_ERROR", message: "Network error prevented inspection." };
  }
  return { code: "UNKNOWN_ERROR", message: "Unexpected error." };
}

export function isNormalizedError(value: unknown): value is NormalizedError {
  return (
    typeof value === "object" &&
    value !== null &&
    "code" in value &&
    "message" in value &&
    typeof (value as NormalizedError).code === "string" &&
    typeof (value as NormalizedError).message === "string"
  );
}
