import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/** Real attachment byte fixtures used by extension upload-flow tests. */

export function textAttachment(name = "fixture-notes.txt"): File {
  return new File([blobPart(new TextEncoder().encode("fixture text attachment\n"))], name, { type: "text/plain" });
}

export function pngAttachment(name = "fixture-image.png"): File {
  return new File([blobPart(base64Bytes("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="))], name, { type: "image/png" });
}

export function pdfAttachment(name = "fixture-document.pdf"): File {
  return fixtureFile("upload-fixture-files/context-risk-business-brief.pdf", name, "application/pdf");
}

export function csvAttachment(name = "bulk-customer-pii.csv"): File {
  return fixtureFile("upload-fixture-files/bulk-customer-pii.csv", name, "text/csv");
}

function fixtureFile(relativePath: string, name: string, type: string): File {
  const bytes = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "../e2e/fixtures", relativePath));
  return new File([blobPart(bytes)], name, { type });
}

function base64Bytes(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function blobPart(bytes: Uint8Array): ArrayBuffer {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}
