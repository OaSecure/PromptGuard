import { describe, expect, it } from "vitest";
import { DEFAULT_CONFIG } from "../../src/shared/constants";
import { validateFilePolicy } from "../../src/shared/filePolicy";

describe("file policy", () => {
  it("allows configured text extensions", () => {
    const [decision] = validateFilePolicy([{ name: "notes.md", size: 128, type: "text/markdown" }], DEFAULT_CONFIG.file_upload);

    expect(decision.allowed).toBe(true);
    expect(decision.extension).toBe(".md");

    const [envDecision] = validateFilePolicy([{ name: ".env", size: 128, type: "text/plain" }], DEFAULT_CONFIG.file_upload);
    expect(envDecision.allowed).toBe(true);
    expect(envDecision.extension).toBe(".env");
  });

  it("compares configured extension lists case-insensitively", () => {
    const [allowed] = validateFilePolicy([{ name: "NOTES.TXT", size: 128, type: "text/plain" }], {
      ...DEFAULT_CONFIG.file_upload,
      allowed_extensions: [".TXT"],
      excluded_extensions: []
    });
    const [excluded] = validateFilePolicy([{ name: "REPORT.PDF", size: 128, type: "application/pdf" }], {
      ...DEFAULT_CONFIG.file_upload,
      allowed_extensions: [".PDF"],
      excluded_extensions: [".PDF"]
    });

    expect(allowed.allowed).toBe(true);
    expect(allowed.extension).toBe(".txt");
    expect(excluded.reason).toBe("excluded_extension");
  });

  it("allows parser and OCR supported attachments while rejecting excluded and uninspectable files", () => {
    const decisions = validateFilePolicy(
      [
        { name: "report.pdf", size: 128, type: "application/pdf" },
        { name: "slides.pptx", size: 128, type: "application/vnd.openxmlformats-officedocument.presentationml.presentation" },
        { name: "archive.zip", size: 128, type: "application/zip" },
        { name: "image.png", size: 128, type: "image/png" },
        { name: "script.js", size: 128, type: "application/octet-stream" }
      ],
      DEFAULT_CONFIG.file_upload
    );

    const [trailingDot] = validateFilePolicy([{ name: "notes.", size: 128, type: "text/plain" }], DEFAULT_CONFIG.file_upload);
    expect(trailingDot.reason).toBe("unsupported_extension");
    expect(decisions.map((decision) => decision.reason)).toEqual([
      undefined,
      undefined,
      "excluded_extension",
      undefined,
      "non_inspectable_mime"
    ]);
  });

  it("enforces disabled, count, per-file size, and batch size policies", () => {
    const disabled = validateFilePolicy([{ name: "notes.txt", size: 128, type: "text/plain" }], {
      ...DEFAULT_CONFIG.file_upload,
      enabled: false
    });
    expect(disabled[0].reason).toBe("disabled");

    const tooMany = validateFilePolicy(
      [
        { name: "a.txt", size: 1, type: "text/plain" },
        { name: "b.txt", size: 1, type: "text/plain" }
      ],
      { ...DEFAULT_CONFIG.file_upload, max_file_count: 1 }
    );
    expect(tooMany.map((decision) => decision.reason)).toEqual(["too_many_files", "too_many_files"]);

    const tooLarge = validateFilePolicy([{ name: "notes.txt", size: 10, type: "text/plain" }], {
      ...DEFAULT_CONFIG.file_upload,
      max_file_size_bytes: 5
    });
    expect(tooLarge[0].reason).toBe("file_too_large");

    const batchTooLarge = validateFilePolicy(
      [
        { name: "a.txt", size: 4, type: "text/plain" },
        { name: "b.txt", size: 4, type: "text/plain" }
      ],
      { ...DEFAULT_CONFIG.file_upload, max_total_size_bytes: 5 }
    );
    expect(batchTooLarge.map((decision) => decision.reason)).toEqual(["batch_too_large", "batch_too_large"]);
  });

  it("treats exact file-count and size limits as allowed and rejects limit plus one", () => {
    const exactCount = validateFilePolicy(
      [
        { name: "a.txt", size: 1, type: "text/plain" },
        { name: "b.txt", size: 1, type: "text/plain" }
      ],
      { ...DEFAULT_CONFIG.file_upload, max_file_count: 2 }
    );
    const overCount = validateFilePolicy(
      [
        { name: "a.txt", size: 1, type: "text/plain" },
        { name: "b.txt", size: 1, type: "text/plain" },
        { name: "c.txt", size: 1, type: "text/plain" }
      ],
      { ...DEFAULT_CONFIG.file_upload, max_file_count: 2 }
    );

    const exactFileSize = validateFilePolicy([{ name: "notes.txt", size: 5, type: "text/plain" }], {
      ...DEFAULT_CONFIG.file_upload,
      max_file_size_bytes: 5
    });
    const overFileSize = validateFilePolicy([{ name: "notes.txt", size: 6, type: "text/plain" }], {
      ...DEFAULT_CONFIG.file_upload,
      max_file_size_bytes: 5
    });

    const exactBatchSize = validateFilePolicy(
      [
        { name: "a.txt", size: 2, type: "text/plain" },
        { name: "b.txt", size: 3, type: "text/plain" }
      ],
      { ...DEFAULT_CONFIG.file_upload, max_total_size_bytes: 5 }
    );
    const overBatchSize = validateFilePolicy(
      [
        { name: "a.txt", size: 2, type: "text/plain" },
        { name: "b.txt", size: 4, type: "text/plain" }
      ],
      { ...DEFAULT_CONFIG.file_upload, max_total_size_bytes: 5 }
    );

    expect(exactCount.every((decision) => decision.allowed)).toBe(true);
    expect(overCount.map((decision) => decision.reason)).toEqual(["too_many_files", "too_many_files", "too_many_files"]);
    expect(exactFileSize[0].allowed).toBe(true);
    expect(overFileSize[0].reason).toBe("file_too_large");
    expect(exactBatchSize.every((decision) => decision.allowed)).toBe(true);
    expect(overBatchSize.map((decision) => decision.reason)).toEqual(["batch_too_large", "batch_too_large"]);
  });

  it("allows empty text files through policy so upload/temp can produce an empty file reference", () => {
    const [decision] = validateFilePolicy([{ name: "empty.txt", size: 0, type: "text/plain" }], DEFAULT_CONFIG.file_upload);

    expect(decision).toMatchObject({ allowed: true, extension: ".txt" });
  });
});
