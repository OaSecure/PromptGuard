import { describe, expect, it } from "vitest";
import { readAllowedTextFiles } from "../../src/content/textFileReader";
import type { FilePolicyDecision } from "../../src/shared/filePolicy";

describe("text file reader", () => {
  it("reads allowed text files in memory", async () => {
    const file = new File(["hello"], "notes.txt", { type: "text/plain" });
    const [result] = await readAllowedTextFiles([snapshot(file)], [allowed(".txt")]);

    expect(result).toMatchObject({
      client_file_id: "file_test",
      extension: ".txt",
      mime_type: "text/plain",
      size_bytes: 5,
      content_text: "hello"
    });
    expect(Object.keys(result)).not.toContain("name");
  });

  it("rejects binary-looking content even when extension and MIME look text-based", async () => {
    const file = new File([new Uint8Array([0, 1, 2, 3, 4, 5])], "notes.txt", { type: "text/plain" });

    await expect(readAllowedTextFiles([snapshot(file)], [allowed(".txt")])).rejects.toThrow("not text");
  });
});

function snapshot(file: File) {
  return {
    client_file_id: "file_test",
    file,
    policyInput: {
      name: file.name,
      size: file.size,
      type: file.type
    }
  };
}

function allowed(extension: string): FilePolicyDecision {
  return { allowed: true, extension };
}

