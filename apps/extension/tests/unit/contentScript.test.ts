import { beforeEach, describe, expect, it, vi } from "vitest";

describe("content script request context", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
    vi.stubGlobal("chrome", undefined);
    document.body.innerHTML = `
      <textarea id="prompt-textarea" aria-label="Prompt"></textarea>
      <button type="submit" data-testid="send-button">Send</button>
    `;
    document.querySelector<HTMLTextAreaElement>("#prompt-textarea")!.value = "safe prompt";
    window.history.replaceState(null, "", "/c/private-thread?token=secret#fragment");
  });

  it("uses origin-only page context and omits path/query/fragment", async () => {
    const { buildPromptAnalyzeRequest } = await import("../../src/content/contentScript");

    const request = buildPromptAnalyzeRequest("ENTER");
    const serialized = JSON.stringify(request);

    expect(request?.context.page_url_origin).toBe(window.location.origin);
    expect(request?.context.ai_service_domain).toBe(window.location.hostname);
    expect(serialized).not.toContain("private-thread");
    expect(serialized).not.toContain("token=secret");
    expect(serialized).not.toContain("fragment");
  });
});
