import { describe, expect, it } from "vitest";
import { extensionFromName, isInspectableMime } from "../../src/shared/fileTypes";

describe("file type helpers", () => {
  it("extracts lowercase extensions without storing original filenames", () => {
    expect(extensionFromName("REPORT.TXT")).toBe(".txt");
    expect(extensionFromName("archive.tar.gz")).toBe(".gz");
    expect(extensionFromName(".env")).toBe(".env");
    expect(extensionFromName("notes.")).toBe(".");
    expect(extensionFromName("README")).toBe("");
  });

  it("recognizes MIME types that can be inspected by text, parser, or OCR paths", () => {
    expect(isInspectableMime("text/plain")).toBe(true);
    expect(isInspectableMime("application/json")).toBe(true);
    expect(isInspectableMime("application/yaml")).toBe(true);
    expect(isInspectableMime("application/javascript")).toBe(true);
    expect(isInspectableMime("application/sql")).toBe(true);
    expect(isInspectableMime("application/json; charset=utf-8")).toBe(true);
    expect(isInspectableMime("application/pdf")).toBe(true);
    expect(isInspectableMime("image/png")).toBe(true);
    expect(isInspectableMime("application/vnd.openxmlformats-officedocument.wordprocessingml.document")).toBe(true);
  });

  it("rejects binary MIME types without a parser or OCR path", () => {
    expect(isInspectableMime("application/octet-stream")).toBe(false);
    expect(isInspectableMime("application/zip")).toBe(false);
  });
});
