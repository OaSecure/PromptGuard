import { beforeEach, describe, expect, it, vi } from "vitest";

describe("content script request context", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
    vi.stubGlobal("chrome", undefined);
    document.body.innerHTML = `
      <section id="history">
        <div
          data-promptguard-attachment-chip
          data-promptguard-extension=".zip"
          data-promptguard-mime="application/zip"
          data-promptguard-size-bytes="777"
        >
          stale-history.zip
        </div>
      </section>
      <form id="composer">
        <textarea id="prompt-textarea" aria-label="Prompt"></textarea>
        <div
          data-promptguard-attachment-chip
          data-promptguard-extension=".png"
          data-promptguard-mime="image/png"
          data-promptguard-size-bytes="2048"
          data-promptguard-attachment-kind="image"
        >
          customer-secret.png
        </div>
        <button type="submit" data-testid="send-button">Send</button>
      </form>
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
    expect(request?.filter_config_revision).toBeTruthy();
    expect(Array.isArray(request?.inputs)).toBe(true);
    expect(request?.inputs.some((input) => input.source === "attachment_chip")).toBe(true);
    expect(request?.inputs).toHaveLength(2);
    expect(serialized).not.toContain("login_id");
    expect(serialized).not.toContain("customer-secret.png");
    expect(serialized).not.toContain("stale-history.zip");
    expect(serialized).not.toContain("private-thread");
    expect(serialized).not.toContain("token=secret");
    expect(serialized).not.toContain("fragment");
  });

  it("does not add placeholder attachment chips to harmless prompt requests", async () => {
    document.body.innerHTML = `
      <form id="composer">
        <textarea id="prompt-textarea" aria-label="Prompt"></textarea>
        <div data-testid="attachment-item"></div>
        <button type="submit" data-testid="send-button">Send</button>
      </form>
    `;
    document.querySelector<HTMLTextAreaElement>("#prompt-textarea")!.value = "안녕";

    const { buildPromptAnalyzeRequest } = await import("../../src/content/contentScript");

    const request = buildPromptAnalyzeRequest("ENTER");

    expect(request?.inputs).toHaveLength(1);
    expect(request?.inputs[0]).toMatchObject({
      kind: "text",
      source: "composer"
    });
    expect(request?.inputs.some((input) => input.kind === "unsupported_attachment")).toBe(false);
  });
});
