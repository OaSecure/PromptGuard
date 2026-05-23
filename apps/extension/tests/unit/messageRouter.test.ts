import { afterEach, describe, expect, it, vi } from "vitest";
import { routeMessage } from "../../src/background/messageRouter";
import { DEFAULT_CONFIG, STORAGE_KEYS } from "../../src/shared/constants";
import { createClientRequestId } from "../../src/shared/hashing";
import type { AnalyzeRequest, AuthMeResponse, ExtensionConfigResponse } from "../../src/shared/types";

describe("message router API auth boundary", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("passes the stored bearer token to the real auth check", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "https://api.promptguard.test",
      [STORAGE_KEYS.mockMode]: false,
      [STORAGE_KEYS.accessToken]: "test-access-token"
    });
    const fetchMock = vi.fn(async () => jsonResponse(authMeResponse()));
    vi.stubGlobal("chrome", { storage: { local: storage } });
    vi.stubGlobal("fetch", fetchMock);

    await routeMessage({ type: "AUTH_ME_REQUEST" });

    expect(fetchMock).toHaveBeenCalledWith("https://api.promptguard.test/auth/me", expect.objectContaining({
      method: "GET",
      headers: expect.objectContaining({
        Authorization: "Bearer test-access-token",
        "X-PromptGuard-Client": "chrome-extension"
      })
    }));
  });

  it("passes the stored bearer token to real config sync and caches only config metadata", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "https://api.promptguard.test",
      [STORAGE_KEYS.mockMode]: false,
      [STORAGE_KEYS.accessToken]: "test-access-token"
    });
    const config = { ...DEFAULT_CONFIG, policy_version: "v-test-config" };
    const fetchMock = vi.fn(async () => jsonResponse(config));
    vi.stubGlobal("chrome", { storage: { local: storage } });
    vi.stubGlobal("fetch", fetchMock);

    await routeMessage({ type: "CONFIG_SYNC_REQUEST" });

    expect(fetchMock).toHaveBeenCalledWith("https://api.promptguard.test/config/extension", expect.objectContaining({
      method: "GET",
      headers: expect.objectContaining({
        Authorization: "Bearer test-access-token",
        "X-PromptGuard-Client": "chrome-extension"
      })
    }));
    expect(storage.snapshot()[STORAGE_KEYS.configCache]).toMatchObject({ policy_version: "v-test-config" });
    expect(JSON.stringify(storage.snapshot()[STORAGE_KEYS.configCache])).not.toContain("test-access-token");
  });

  it("does not cache malformed config responses", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "https://api.promptguard.test",
      [STORAGE_KEYS.mockMode]: false,
      [STORAGE_KEYS.accessToken]: "test-access-token"
    });
    const fetchMock = vi.fn(async () => jsonResponse({ policy_version: "v-malformed" }));
    vi.stubGlobal("chrome", { storage: { local: storage } });
    vi.stubGlobal("fetch", fetchMock);

    const response = await routeMessage({ type: "CONFIG_SYNC_REQUEST" });

    expect(response).toEqual({
      code: "VALIDATION_ERROR",
      message: "Config response could not be processed."
    });
    expect(storage.snapshot()[STORAGE_KEYS.configCache]).toBeUndefined();
  });

  it("routes prompt analysis through the fake backend in mock mode", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "https://api.promptguard.test",
      [STORAGE_KEYS.mockMode]: true
    });
    const fetchMock = vi.fn();
    vi.stubGlobal("chrome", { storage: { local: storage } });
    vi.stubGlobal("fetch", fetchMock);

    const response = await routeMessage({ type: "PROMPT_ANALYZE_REQUEST", payload: analyzeRequest("contact member@example.com") });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(response).toMatchObject({
      decision: {
        action: "Mask",
        allow_original_send: false
      },
      masked_prompt: "contact [masked-email]"
    });
  });
});

function createStorage(initial: Record<string, unknown>) {
  const values = { ...initial };
  return {
    async get(keys: string | string[]) {
      if (Array.isArray(keys)) {
        return Object.fromEntries(keys.map((key) => [key, values[key]]));
      }
      return { [keys]: values[keys] };
    },
    async set(entries: Record<string, unknown>) {
      Object.assign(values, entries);
    },
    async remove(keys: string | string[]) {
      for (const key of Array.isArray(keys) ? keys : [keys]) {
        delete values[key];
      }
    },
    snapshot() {
      return { ...values };
    }
  };
}

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    json: async () => body
  } as Response;
}

function authMeResponse(): AuthMeResponse {
  return {
    id: "user_test",
    workspace_id: "workspace_test",
    email: "member@example.com",
    role: "USER",
    status: "ACTIVE",
    policy_version: "v-test-config"
  };
}

function analyzeRequest(text: string): AnalyzeRequest {
  return {
    prompt: {
      text,
      input_method: "ENTER",
      content_length: text.length
    },
    context: {
      ai_service: "CHATGPT",
      ai_service_domain: "chatgpt.com",
      page_url_origin: "https://chatgpt.com",
      extension_version: "0.4.0",
      browser: "Chrome",
      locale: "ko-KR"
    },
    policy: { version: DEFAULT_CONFIG.policy_version },
    client_request_id: createClientRequestId("crq")
  };
}
