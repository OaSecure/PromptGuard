/** Real attachment byte fixtures used by extension upload-flow tests. */

export function textAttachment(name = "fixture-notes.txt"): File {
  return new File([blobPart(new TextEncoder().encode("fixture text attachment\n"))], name, { type: "text/plain" });
}

export function pngAttachment(name = "fixture-image.png"): File {
  return new File([blobPart(base64Bytes("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="))], name, { type: "image/png" });
}

export function pdfAttachment(name = "fixture-document.pdf"): File {
  return new File(
    [
      blobPart(new TextEncoder().encode(
        "%PDF-1.4\n" +
          "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n" +
          "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n" +
          "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R >>\nendobj\n" +
          "4 0 obj\n<< /Length 44 >>\nstream\nBT /F1 12 Tf 20 100 Td (PromptGuard PDF) Tj ET\nendstream\nendobj\n" +
          "xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000204 00000 n \n" +
          "trailer\n<< /Root 1 0 R /Size 5 >>\nstartxref\n298\n%%EOF\n"
      ))
    ],
    name,
    { type: "application/pdf" }
  );
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
