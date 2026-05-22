import { describe, expect, it } from "vitest";
import { extensionFromName, isLikelyTextMime } from "../../src/shared/fileTypes";

describe("file type helpers", () => {
  it("extracts lowercase extensions without storing original filenames", () => {
    expect(extensionFromName("REPORT.TXT")).toBe(".txt");
    expect(extensionFromName("archive.tar.gz")).toBe(".gz");
    expect(extensionFromName(".env")).toBe(".env");
    expect(extensionFromName("notes.")).toBe(".");
    expect(extensionFromName("README")).toBe("");
  });

  it("recognizes common text-oriented MIME types", () => {
    expect(isLikelyTextMime("text/plain")).toBe(true);
    expect(isLikelyTextMime("application/json")).toBe(true);
    expect(isLikelyTextMime("application/yaml")).toBe(true);
    expect(isLikelyTextMime("application/javascript")).toBe(true);
    expect(isLikelyTextMime("application/sql")).toBe(true);
    expect(isLikelyTextMime("application/json; charset=utf-8")).toBe(true);
  });

  it("rejects binary-oriented MIME types", () => {
    expect(isLikelyTextMime("application/octet-stream")).toBe(false);
    expect(isLikelyTextMime("application/pdf")).toBe(false);
    expect(isLikelyTextMime("image/png")).toBe(false);
  });
});
