import { describe, expect, it } from "vitest";
import { createFileUploadSnapshots } from "../../src/content/fileUploadSnapshot";

describe("file upload snapshots", () => {
  it("uses opaque per-attempt client file IDs instead of filename hashes", () => {
    const files = [
      new File(["first"], "customer-project.env", { type: "text/plain" }),
      new File(["second"], "customer-project.env", { type: "text/plain" })
    ];

    const snapshots = createFileUploadSnapshots(files);
    const payload = JSON.stringify(snapshots.map(({ client_file_id, policyInput }) => ({ client_file_id, policyInput })));

    expect(snapshots).toHaveLength(2);
    expect(snapshots[0].client_file_id).toMatch(/^file_/);
    expect(snapshots[1].client_file_id).toMatch(/^file_/);
    expect(snapshots[0].client_file_id).not.toBe(snapshots[1].client_file_id);
    expect(snapshots[0].client_file_id).not.toContain("customer");
    expect(snapshots[0].client_file_id).not.toContain("project");
    expect(snapshots[0].client_file_id).not.toContain("env");
    expect(payload).toContain("customer-project.env");
  });
});
