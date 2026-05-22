import { describe, expect, it } from "vitest";
import { sanitizeForDiagnostics } from "../../src/shared/sanitize";

describe("privacy regression", () => {
  it("redacts forbidden diagnostic fields", () => {
    const seeded = {
      raw_prompt: "SEEDED_PROMPT_SHOULD_NOT_SURVIVE",
      file_content: "SEEDED_FILE_SHOULD_NOT_SURVIVE",
      content_text: "SEEDED_CONTENT_TEXT_SHOULD_NOT_SURVIVE",
      text: "SEEDED_TEXT_SHOULD_NOT_SURVIVE",
      masked_prompt: "SEEDED_MASKED_PROMPT_SHOULD_NOT_SURVIVE",
      filename: "customer-project.env",
      originalFileName: "quarterly-plan.txt",
      nested: {
        detectedRawValue: "secret-value",
        extractedText: "copied sensitive phrase",
        safe: "metadata"
      }
    };

    const redacted = JSON.stringify(sanitizeForDiagnostics(seeded));

    expect(redacted).not.toContain("SEEDED_PROMPT_SHOULD_NOT_SURVIVE");
    expect(redacted).not.toContain("SEEDED_FILE_SHOULD_NOT_SURVIVE");
    expect(redacted).not.toContain("SEEDED_CONTENT_TEXT_SHOULD_NOT_SURVIVE");
    expect(redacted).not.toContain("SEEDED_TEXT_SHOULD_NOT_SURVIVE");
    expect(redacted).not.toContain("SEEDED_MASKED_PROMPT_SHOULD_NOT_SURVIVE");
    expect(redacted).not.toContain("customer-project.env");
    expect(redacted).not.toContain("quarterly-plan.txt");
    expect(redacted).not.toContain("secret-value");
    expect(redacted).not.toContain("copied sensitive phrase");
    expect(redacted).toContain("metadata");
  });
});
