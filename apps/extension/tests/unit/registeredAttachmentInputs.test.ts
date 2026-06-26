import { afterEach, describe, expect, it } from "vitest";
import type { AnalyzeInput } from "../../src/shared/types";
import {
  clearRegisteredAttachmentInputs,
  getOrCreateRegisteredAttachmentRequestId,
  getRegisteredAttachmentInputs,
  getRegisteredAttachmentRequestId,
  registerAttachmentInputs
} from "../../src/content/registeredAttachmentInputs";

describe("registered attachment inputs", () => {
  afterEach(() => {
    clearRegisteredAttachmentInputs();
  });

  it("drops late temp-upload results after the owning attachment state is cleared", () => {
    const requestId = getOrCreateRegisteredAttachmentRequestId();

    clearRegisteredAttachmentInputs();
    registerAttachmentInputs([fileInput()], requestId);

    expect(getRegisteredAttachmentInputs()).toEqual([]);
    expect(getRegisteredAttachmentRequestId()).toBeUndefined();
  });

  it("keeps temp-upload results only for the active attachment request id", () => {
    const requestId = getOrCreateRegisteredAttachmentRequestId();

    registerAttachmentInputs([fileInput()], "crq_stale_owner");
    expect(getRegisteredAttachmentInputs()).toEqual([]);

    registerAttachmentInputs([fileInput()], requestId);
    expect(getRegisteredAttachmentInputs()).toHaveLength(1);
    expect(getRegisteredAttachmentRequestId()).toBe(requestId);
  });
});

function fileInput(): AnalyzeInput {
  return {
    input_id: "in_registered_file_ref_test",
    kind: "file_reference",
    source: "attached_file",
    size_bytes: 1024,
    content_included: false,
    file_ref: "fref_registeredabcdefghijklmnop",
    temp_scope_id: "tscope_registeredabcdefghijkl",
    file_kind: "image",
    mime: "image/png",
    extension: "png",
    size_bucket: "small"
  };
}
