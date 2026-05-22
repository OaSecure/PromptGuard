import { describe, expect, it } from "vitest";
import manifest from "../../manifest.json";

describe("manifest permission boundary", () => {
  it("keeps MVP permissions narrow and excludes network monitoring permissions", () => {
    const forbiddenPermissions = ["web" + "Request", "declarative" + "NetRequest"];

    expect(manifest.permissions).toEqual(["storage"]);
    for (const permission of forbiddenPermissions) {
      expect(manifest.permissions).not.toContain(permission);
    }
    expect(manifest.host_permissions).toEqual([
      "https://chatgpt.com/*",
      "https://chat.openai.com/*",
      "https://promptguard.example.com/*"
    ]);
  });

  it("does not inject the content script into the API origin", () => {
    expect(manifest.content_scripts[0].matches).toEqual([
      "https://chatgpt.com/*",
      "https://chat.openai.com/*"
    ]);
    expect(manifest.content_scripts[0].matches).not.toContain("https://promptguard.example.com/*");
    expect(manifest.content_scripts[0].run_at).toBe("document_start");
  });
});
