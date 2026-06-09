import { describe, expect, it } from "vitest";
import { collectAttachmentChipInputs } from "../../src/content/attachmentChipCapture";

describe("attachment chip capture", () => {
  it("captures metadata-only attachment chips without leaking visible labels", () => {
    document.body.innerHTML = `
      <div
        data-promptguard-attachment-chip
        data-promptguard-extension=".png"
        data-promptguard-mime="image/png"
        data-promptguard-size-bytes="2048"
        data-promptguard-attachment-kind="image"
      >
        customer-secret.png
      </div>
    `;

    const inputs = collectAttachmentChipInputs(document, { attachment_chip: ["[data-promptguard-attachment-chip]"] });

    expect(inputs).toHaveLength(1);
    expect(inputs[0]).toMatchObject({
      kind: "attachment_metadata",
      source: "attachment_chip",
      content_included: false,
      size_bytes: 2048,
      metadata: {
        extension: "png",
        mime: "image/png",
        attachment_kind: "image",
        attachment_index: 0
      }
    });
    expect(JSON.stringify(inputs)).not.toContain("customer-secret.png");
  });

  it("falls back to unsupported attachment when chip metadata is unavailable", () => {
    document.body.innerHTML = `<div data-promptguard-attachment-chip>financial-report.pdf</div>`;

    const inputs = collectAttachmentChipInputs(document, { attachment_chip: ["[data-promptguard-attachment-chip]"] });

    expect(inputs).toHaveLength(1);
    expect(inputs[0]).toMatchObject({
      kind: "unsupported_attachment",
      source: "attachment_chip",
      content_included: false
    });
    expect(JSON.stringify(inputs)).not.toContain("financial-report.pdf");
  });
});
