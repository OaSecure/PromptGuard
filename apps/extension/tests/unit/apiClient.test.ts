import { afterEach, describe, expect, it, vi } from "vitest";
import { apiUrl, getJson, postJson } from "../../src/background/apiClient";

describe("api client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("joins configured API base URLs without introducing double slashes", () => {
    expect(apiUrl("https://api.promptguard.test/api/v1", "/auth/me")).toBe("https://api.promptguard.test/api/v1/auth/me");
    expect(apiUrl("https://api.promptguard.test/api/v1/", "/auth/me")).toBe("https://api.promptguard.test/api/v1/auth/me");
    expect(apiUrl("https://api.promptguard.test/api/v1/", "auth/me")).toBe("https://api.promptguard.test/api/v1/auth/me");
  });

  it("sends bearer auth and JSON headers for POST requests", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await postJson("/prompts/analyze", { sample: "metadata" }, {
      baseUrl: "https://api.promptguard.test/api/v1/",
      token: "test-access-token",
      timeoutMs: 50
    });

    expect(fetchMock).toHaveBeenCalledWith("https://api.promptguard.test/api/v1/prompts/analyze", expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({
        Authorization: "Bearer test-access-token",
        "Content-Type": "application/json",
        "X-PromptGuard-Client": "chrome-extension"
      }),
      body: JSON.stringify({ sample: "metadata" })
    }));
  });

  it("sends bearer auth for GET requests", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await getJson("/config/extension", {
      baseUrl: "https://api.promptguard.test/api/v1/",
      token: "test-access-token",
      timeoutMs: 50
    });

    expect(fetchMock).toHaveBeenCalledWith("https://api.promptguard.test/api/v1/config/extension", expect.objectContaining({
      method: "GET",
      headers: expect.objectContaining({
        Authorization: "Bearer test-access-token",
        "X-PromptGuard-Client": "chrome-extension"
      })
    }));
  });
});

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    json: async () => body
  } as Response;
}

