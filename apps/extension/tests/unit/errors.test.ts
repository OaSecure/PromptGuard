import { describe, expect, it } from "vitest";
import { normalizeError } from "../../src/shared/errors";

describe("error normalization", () => {
  it("normalizes timeout and network errors with fixed safe messages", () => {
    const timeout = new Error("https://example.test/path?token=secret");
    timeout.name = "AbortError";

    expect(normalizeError(timeout)).toEqual({
      code: "TIMEOUT",
      message: "Inspection timed out and the action is held."
    });
    expect(normalizeError(new TypeError("https://example.test/path?token=secret"))).toEqual({
      code: "NETWORK_ERROR",
      message: "Network error prevented inspection."
    });
  });

  it("does not echo arbitrary error messages", () => {
    const normalized = normalizeError(new Error("raw-looking-value should not be returned"));

    expect(normalized).toEqual({
      code: "UNKNOWN_ERROR",
      message: "Unexpected error."
    });
    expect(normalized.message).not.toContain("raw-looking-value");
  });
});

