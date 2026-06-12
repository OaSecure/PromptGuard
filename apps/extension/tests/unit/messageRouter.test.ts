import { afterEach, describe, expect, it, vi } from "vitest";
import { routeMessage } from "../../src/background/messageRouter";
import { createAnalyzeRequest, createComposerInput, createFileTextInput } from "../../src/shared/analyzeRequestBuilder";
import { DEFAULT_CONFIG, STORAGE_KEYS } from "../../src/shared/constants";
import type { AnalyzeRequest, AuthMeResponse } from "../../src/shared/types";

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

  it("calls real login and stores the returned token pair", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "https://api.promptguard.test",
      [STORAGE_KEYS.mockMode]: false
    });
    const fetchMock = vi.fn(async () => jsonResponse({ access_token: "test-access-token", refresh_token: "test-refresh-token" }));
    vi.stubGlobal("chrome", { storage: { local: storage } });
    vi.stubGlobal("fetch", fetchMock);

    const response = await routeMessage({ type: "AUTH_LOGIN_REQUEST", payload: { login_id: " member@example.com ", password: " test-password " } });

    expect(response).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith("https://api.promptguard.test/auth/login", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ login_id: "member@example.com", password: "test-password" })
    }));
    expect(storage.snapshot()).toMatchObject({
      [STORAGE_KEYS.accessToken]: "test-access-token",
      [STORAGE_KEYS.refreshToken]: "test-refresh-token"
    });
    expect(JSON.stringify(response)).not.toContain("test-password");
  });

  it("rejects malformed real login responses without storing a partial token pair", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "https://api.promptguard.test",
      [STORAGE_KEYS.mockMode]: false
    });
    const fetchMock = vi.fn(async () => jsonResponse({ access_token: "test-access-token" }));
    vi.stubGlobal("chrome", { storage: { local: storage } });
    vi.stubGlobal("fetch", fetchMock);

    const response = await routeMessage({ type: "AUTH_LOGIN_REQUEST", payload: { login_id: "member@example.com", password: "test-password" } });

    expect(response).toEqual({ code: "VALIDATION_ERROR", message: "Login response could not be processed." });
    expect(storage.snapshot()[STORAGE_KEYS.accessToken]).toBeUndefined();
    expect(storage.snapshot()[STORAGE_KEYS.refreshToken]).toBeUndefined();
    expect(JSON.stringify(response)).not.toContain("test-password");
  });

  it("logs out through the real API with bearer and refresh ownership then clears auth state", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "https://api.promptguard.test",
      [STORAGE_KEYS.mockMode]: false,
      [STORAGE_KEYS.accessToken]: "test-access-token",
      [STORAGE_KEYS.refreshToken]: "stored-refresh-token"
    });
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("chrome", { storage: { local: storage } });
    vi.stubGlobal("fetch", fetchMock);

    const response = await routeMessage({ type: "AUTH_LOGOUT_REQUEST" });

    expect(response).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith("https://api.promptguard.test/auth/logout", expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({
        Authorization: "Bearer test-access-token",
        "X-PromptGuard-Client": "chrome-extension"
      }),
      body: JSON.stringify({ refresh_token: "stored-refresh-token" })
    }));
    expect(storage.snapshot()[STORAGE_KEYS.accessToken]).toBeUndefined();
    expect(storage.snapshot()[STORAGE_KEYS.refreshToken]).toBeUndefined();
  });

  it("clears local auth state on logout even when the server rejects the stale refresh token", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "https://api.promptguard.test",
      [STORAGE_KEYS.mockMode]: false,
      [STORAGE_KEYS.accessToken]: "expired-access-token",
      [STORAGE_KEYS.refreshToken]: "stored-refresh-token"
    });
    const fetchMock = vi.fn(async () => statusResponse(401, { error: "raw server body with stored-refresh-token" }));
    vi.stubGlobal("chrome", { storage: { local: storage } });
    vi.stubGlobal("fetch", fetchMock);

    const response = await routeMessage({ type: "AUTH_LOGOUT_REQUEST" });

    expect(response).toEqual({ code: "UNAUTHORIZED", message: "Login expired. Sign in again." });
    expect(JSON.stringify(response)).not.toContain("stored-refresh-token");
    expect(JSON.stringify(response)).not.toContain("raw server body");
    expect(storage.snapshot()[STORAGE_KEYS.accessToken]).toBeUndefined();
    expect(storage.snapshot()[STORAGE_KEYS.refreshToken]).toBeUndefined();
  });

  it("refreshes once after real auth check returns 401 and retries with the new access token", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "https://api.promptguard.test",
      [STORAGE_KEYS.mockMode]: false,
      [STORAGE_KEYS.accessToken]: "expired-access-token",
      [STORAGE_KEYS.refreshToken]: "stored-refresh-token"
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(statusResponse(401))
      .mockResolvedValueOnce(jsonResponse({ access_token: "new-access-token", refresh_token: "new-refresh-token" }))
      .mockResolvedValueOnce(jsonResponse(authMeResponse()));
    vi.stubGlobal("chrome", { storage: { local: storage } });
    vi.stubGlobal("fetch", fetchMock);

    const response = await routeMessage({ type: "AUTH_ME_REQUEST" });

    expect(response).toMatchObject({ email: "member@example.com" });
    expect(fetchMock).toHaveBeenNthCalledWith(2, "https://api.promptguard.test/auth/refresh", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ refresh_token: "stored-refresh-token" })
    }));
    expect(fetchMock).toHaveBeenNthCalledWith(3, "https://api.promptguard.test/auth/me", expect.objectContaining({
      method: "GET",
      headers: expect.objectContaining({ Authorization: "Bearer new-access-token" })
    }));
    expect(storage.snapshot()).toMatchObject({
      [STORAGE_KEYS.accessToken]: "new-access-token",
      [STORAGE_KEYS.refreshToken]: "new-refresh-token"
    });
  });

  it("shares one refresh call across concurrent 401 responses", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "https://api.promptguard.test",
      [STORAGE_KEYS.mockMode]: false,
      [STORAGE_KEYS.accessToken]: "expired-access-token",
      [STORAGE_KEYS.refreshToken]: "stored-refresh-token"
    });
    let authMeCalls = 0;
    let resolveRefresh!: (response: Response) => void;
    const refreshResponse = new Promise<Response>((resolve) => {
      resolveRefresh = resolve;
    });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/refresh")) {
        return refreshResponse;
      }
      if (url.endsWith("/auth/me")) {
        authMeCalls += 1;
        return Promise.resolve(authMeCalls <= 2 ? statusResponse(401) : jsonResponse(authMeResponse()));
      }
      return Promise.resolve(statusResponse(404));
    });
    vi.stubGlobal("chrome", { storage: { local: storage } });
    vi.stubGlobal("fetch", fetchMock);

    const first = routeMessage({ type: "AUTH_ME_REQUEST" });
    const second = routeMessage({ type: "AUTH_ME_REQUEST" });

    await waitForFetchCount(fetchMock, 3);
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/auth/refresh"))).toHaveLength(1);

    resolveRefresh(jsonResponse({ access_token: "new-access-token" }));
    const responses = await Promise.all([first, second]);

    expect(responses).toEqual([authMeResponse(), authMeResponse()]);
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/auth/me"))).toHaveLength(4);
    expect(storage.snapshot()).toMatchObject({
      [STORAGE_KEYS.accessToken]: "new-access-token",
      [STORAGE_KEYS.refreshToken]: "stored-refresh-token"
    });
  });

  it("clears stale auth when the retried auth check still returns 401 after refresh", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "https://api.promptguard.test",
      [STORAGE_KEYS.mockMode]: false,
      [STORAGE_KEYS.accessToken]: "expired-access-token",
      [STORAGE_KEYS.refreshToken]: "stored-refresh-token"
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(statusResponse(401))
      .mockResolvedValueOnce(jsonResponse({ access_token: "new-access-token" }))
      .mockResolvedValueOnce(statusResponse(401));
    vi.stubGlobal("chrome", { storage: { local: storage } });
    vi.stubGlobal("fetch", fetchMock);

    const response = await routeMessage({ type: "AUTH_ME_REQUEST" });

    expect(response).toEqual({ code: "UNAUTHORIZED", message: "Login expired. Sign in again." });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(storage.snapshot()[STORAGE_KEYS.accessToken]).toBeUndefined();
    expect(storage.snapshot()[STORAGE_KEYS.refreshToken]).toBeUndefined();
  });

  it("does not refresh without a stored refresh token", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "https://api.promptguard.test",
      [STORAGE_KEYS.mockMode]: false,
      [STORAGE_KEYS.accessToken]: "expired-access-token"
    });
    const fetchMock = vi.fn(async () => statusResponse(401));
    vi.stubGlobal("chrome", { storage: { local: storage } });
    vi.stubGlobal("fetch", fetchMock);

    const response = await routeMessage({ type: "AUTH_ME_REQUEST" });

    expect(response).toEqual({ code: "UNAUTHORIZED", message: "Login expired. Sign in again." });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("clears stale auth and hides server body when refresh fails", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "https://api.promptguard.test",
      [STORAGE_KEYS.mockMode]: false,
      [STORAGE_KEYS.accessToken]: "expired-access-token",
      [STORAGE_KEYS.refreshToken]: "stored-refresh-token"
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(statusResponse(401))
      .mockResolvedValueOnce(statusResponse(401, { error: "raw server body with stored-refresh-token" }));
    vi.stubGlobal("chrome", { storage: { local: storage } });
    vi.stubGlobal("fetch", fetchMock);

    const response = await routeMessage({ type: "AUTH_ME_REQUEST" });

    expect(response).toEqual({ code: "UNAUTHORIZED", message: "Login expired. Sign in again." });
    expect(JSON.stringify(response)).not.toContain("stored-refresh-token");
    expect(JSON.stringify(response)).not.toContain("raw server body");
    expect(storage.snapshot()[STORAGE_KEYS.accessToken]).toBeUndefined();
    expect(storage.snapshot()[STORAGE_KEYS.refreshToken]).toBeUndefined();
  });

  it("clears stale auth and returns a safe error when refresh response is malformed", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "https://api.promptguard.test",
      [STORAGE_KEYS.mockMode]: false,
      [STORAGE_KEYS.accessToken]: "expired-access-token",
      [STORAGE_KEYS.refreshToken]: "stored-refresh-token"
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(statusResponse(401))
      .mockResolvedValueOnce(jsonResponse({ refresh_token: "rotated-refresh-without-access" }));
    vi.stubGlobal("chrome", { storage: { local: storage } });
    vi.stubGlobal("fetch", fetchMock);

    const response = await routeMessage({ type: "AUTH_ME_REQUEST" });

    expect(response).toEqual({ code: "UNAUTHORIZED", message: "Login expired. Sign in again." });
    expect(JSON.stringify(response)).not.toContain("rotated-refresh-without-access");
    expect(storage.snapshot()[STORAGE_KEYS.accessToken]).toBeUndefined();
    expect(storage.snapshot()[STORAGE_KEYS.refreshToken]).toBeUndefined();
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

  it("refreshes config sync after 401 and retries with the new access token", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "https://api.promptguard.test",
      [STORAGE_KEYS.mockMode]: false,
      [STORAGE_KEYS.accessToken]: "expired-access-token",
      [STORAGE_KEYS.refreshToken]: "stored-refresh-token"
    });
    const config = { ...DEFAULT_CONFIG, policy_version: "v-refreshed-config" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(statusResponse(401))
      .mockResolvedValueOnce(jsonResponse({ access_token: "new-access-token" }))
      .mockResolvedValueOnce(jsonResponse(config));
    vi.stubGlobal("chrome", { storage: { local: storage } });
    vi.stubGlobal("fetch", fetchMock);

    const response = await routeMessage({ type: "CONFIG_SYNC_REQUEST" });

    expect(response).toMatchObject({ policy_version: "v-refreshed-config" });
    expect(fetchMock).toHaveBeenNthCalledWith(3, "https://api.promptguard.test/config/extension", expect.objectContaining({
      method: "GET",
      headers: expect.objectContaining({ Authorization: "Bearer new-access-token" })
    }));
    expect(storage.snapshot()[STORAGE_KEYS.configCache]).toMatchObject({ policy_version: "v-refreshed-config" });
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
      action: "Mask",
      allow_original_send: false,
      masked_prompt: "contact [masked-email]"
    });
  });

  it("refreshes prompt analysis after 401 and retries with the new access token", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "https://api.promptguard.test",
      [STORAGE_KEYS.mockMode]: false,
      [STORAGE_KEYS.accessToken]: "expired-access-token",
      [STORAGE_KEYS.refreshToken]: "stored-refresh-token"
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(statusResponse(401))
      .mockResolvedValueOnce(jsonResponse({ access_token: "new-access-token" }))
      .mockResolvedValueOnce(jsonResponse(analyzeResponse()));
    vi.stubGlobal("chrome", { storage: { local: storage } });
    vi.stubGlobal("fetch", fetchMock);

    const response = await routeMessage({ type: "PROMPT_ANALYZE_REQUEST", payload: analyzeRequest("safe prompt") });

    expect(response).toMatchObject({ request_id: "req_test_prompt" });
    expect(fetchMock).toHaveBeenNthCalledWith(3, "https://api.promptguard.test/prompts/analyze", expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ Authorization: "Bearer new-access-token" })
    }));
  });

  it("refreshes file analysis after 401 and retries with the new access token", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "https://api.promptguard.test",
      [STORAGE_KEYS.mockMode]: false,
      [STORAGE_KEYS.accessToken]: "expired-access-token",
      [STORAGE_KEYS.refreshToken]: "stored-refresh-token"
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(statusResponse(401))
      .mockResolvedValueOnce(jsonResponse({ access_token: "new-access-token" }))
      .mockResolvedValueOnce(jsonResponse(filesAnalyzeResponse()));
    vi.stubGlobal("chrome", { storage: { local: storage } });
    vi.stubGlobal("fetch", fetchMock);

    const response = await routeMessage({ type: "FILES_ANALYZE_REQUEST", payload: filesAnalyzeRequest() });

    expect(response).toMatchObject({ request_id: "req_test_files" });
    expect(fetchMock).toHaveBeenNthCalledWith(3, "https://api.promptguard.test/prompts/analyze", expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ Authorization: "Bearer new-access-token" })
    }));
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
    status: 200,
    json: async () => body
  } as Response;
}

function statusResponse(status: number, body: unknown = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body
  } as Response;
}

async function waitForFetchCount(fetchMock: ReturnType<typeof vi.fn>, count: number): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (fetchMock.mock.calls.length >= count) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  throw new Error(`Expected fetch to be called at least ${count} times, got ${fetchMock.mock.calls.length}.`);
}

function authMeResponse(): AuthMeResponse {
  return {
    id: "user_test",
    workspace_id: "workspace_test",
    email: "member@example.com",
    role: "USER",
    status: "ACTIVE"
  };
}

function analyzeRequest(text: string): AnalyzeRequest {
  return createAnalyzeRequest(
    {
      ai_service: "CHATGPT",
      ai_service_domain: "chatgpt.com",
      page_url_origin: "https://chatgpt.com",
      extension_version: "0.4.0",
      browser: "Chrome",
      locale: "ko-KR"
    },
    DEFAULT_CONFIG.policy_version,
    [createComposerInput({ text, inputMethod: "ENTER" })]
  );
}

function filesAnalyzeRequest(): AnalyzeRequest {
  return createAnalyzeRequest(
    {
      ai_service: "CHATGPT",
      ai_service_domain: "chatgpt.com",
      page_url_origin: "https://chatgpt.com",
      extension_version: "0.4.0",
      browser: "Chrome",
      locale: "ko-KR"
    },
    DEFAULT_CONFIG.policy_version,
    [createFileTextInput({ extension: ".txt", mimeType: "text/plain", sizeBytes: 11, text: "safe file" })]
  );
}

function analyzeResponse(clientRequestId = "crq_test", filterConfigRevision = DEFAULT_CONFIG.policy_version) {
  return {
    event_id: "evt_test_prompt",
    request_id: "req_test_prompt",
    action: "Allow",
    checked_at: "2026-06-09T00:00:00Z",
    risk_score: 1,
    risk_level: "low",
    user_message: "Allowed.",
    allow_original_send: true,
    requires_user_confirmation: false,
    detections: [],
    input_results: [],
    content_unavailable_inputs: [],
    business_context_matches: [],
    client_request_id: clientRequestId,
    filter_config_revision: filterConfigRevision
  };
}

function filesAnalyzeResponse() {
  return {
    ...analyzeResponse("frq_test"),
    event_id: "evt_test_files",
    request_id: "req_test_files"
  };
}
