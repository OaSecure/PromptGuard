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

  it("ignores placeholder chips when metadata is unavailable", () => {
    document.body.innerHTML = `<div data-promptguard-attachment-chip>financial-report.pdf</div>`;

    const inputs = collectAttachmentChipInputs(document, { attachment_chip: ["[data-promptguard-attachment-chip]"] });

    expect(inputs).toEqual([]);
    expect(JSON.stringify(inputs)).not.toContain("financial-report.pdf");
  });

  it("ignores hidden attachment chips left behind by the host page", () => {
    document.body.innerHTML = `
      <div
        data-promptguard-attachment-chip
        data-promptguard-extension=".pdf"
        data-promptguard-mime="application/pdf"
        data-promptguard-size-bytes="2048"
        style="display: none"
      >
        removed-report.pdf
      </div>
    `;

    const inputs = collectAttachmentChipInputs(document, { attachment_chip: ["[data-promptguard-attachment-chip]"] });

    expect(inputs).toEqual([]);
  });

  it("captures image chips that expose an image signal without leaking labels", () => {
    document.body.innerHTML = `
      <div data-testid="attachment-item">
        <img alt="uploaded preview" src="data:image/png;base64,AA==" />
        customer-secret.png
      </div>
    `;

    const inputs = collectAttachmentChipInputs(document, { attachment_chip: ["[data-testid='attachment-item']"] });

    expect(inputs).toHaveLength(1);
    expect(inputs[0]).toMatchObject({
      kind: "attachment_metadata",
      source: "attachment_chip",
      content_included: false,
      metadata: {
        extension: "",
        mime: "image/unknown",
        attachment_kind: "image",
        attachment_index: 0
      }
    });
    expect(JSON.stringify(inputs)).not.toContain("customer-secret.png");
  });
});
