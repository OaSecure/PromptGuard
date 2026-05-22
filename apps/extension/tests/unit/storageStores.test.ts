import { afterEach, describe, expect, it, vi } from "vitest";
import { clearAuthState, getAuthState, saveAccessToken } from "../../src/background/authStore";
import { getSettings, saveApiBaseUrl, saveConfig, saveMockMode } from "../../src/background/configStore";
import { DEFAULT_CONFIG, STORAGE_KEYS } from "../../src/shared/constants";

describe("config and auth storage boundaries", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses defaults when operational settings are not stored", async () => {
    const storage = createStorage({});
    vi.stubGlobal("chrome", { storage: { local: storage } });

    const settings = await getSettings();

    expect(settings).toMatchObject({
      apiBaseUrl: DEFAULT_CONFIG.api_base_url,
      mockMode: true,
      config: DEFAULT_CONFIG
    });
  });

  it("stores only configured operational keys for API URL, mock mode, and config cache", async () => {
    const storage = createStorage({});
    vi.stubGlobal("chrome", { storage: { local: storage } });

    await saveApiBaseUrl("https://api.promptguard.test/api/v1");
    await saveMockMode(false);
    await saveConfig({ ...DEFAULT_CONFIG, policy_version: "v-storage-test" });

    const snapshot = storage.snapshot();
    expect(Object.keys(snapshot).sort()).toEqual([
      STORAGE_KEYS.apiBaseUrl,
      STORAGE_KEYS.configCache,
      STORAGE_KEYS.lastConfigSyncAt,
      STORAGE_KEYS.mockMode
    ].sort());
    expect(snapshot[STORAGE_KEYS.configCache]).toMatchObject({ policy_version: "v-storage-test" });
    expect(JSON.stringify(snapshot)).not.toContain("raw_prompt");
    expect(JSON.stringify(snapshot)).not.toContain("file_content");
  });

  it("normalizes blank or padded API URLs", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.apiBaseUrl]: "   "
    });
    vi.stubGlobal("chrome", { storage: { local: storage } });

    expect((await getSettings()).apiBaseUrl).toBe(DEFAULT_CONFIG.api_base_url);

    await saveApiBaseUrl("  https://api.promptguard.test/api/v1  ");
    expect(storage.snapshot()[STORAGE_KEYS.apiBaseUrl]).toBe("https://api.promptguard.test/api/v1");
  });

  it("falls back to the default API URL when cached config has a blank API URL", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.configCache]: { ...DEFAULT_CONFIG, api_base_url: " " }
    });
    vi.stubGlobal("chrome", { storage: { local: storage } });

    expect((await getSettings()).apiBaseUrl).toBe(DEFAULT_CONFIG.api_base_url);
  });

  it("ignores malformed cached config objects on read", async () => {
    const storage = createStorage({
      [STORAGE_KEYS.configCache]: { policy_version: "v-malformed-cache" }
    });
    vi.stubGlobal("chrome", { storage: { local: storage } });

    const settings = await getSettings();

    expect(settings.config).toBe(DEFAULT_CONFIG);
    expect(settings.apiBaseUrl).toBe(DEFAULT_CONFIG.api_base_url);
  });

  it("stores and clears auth tokens only through auth keys", async () => {
    const storage = createStorage({});
    vi.stubGlobal("chrome", { storage: { local: storage } });

    await saveAccessToken("test-access-token");
    expect(await getAuthState()).toEqual({ accessToken: "test-access-token" });

    await saveAccessToken("  padded-token  ");
    expect(await getAuthState()).toEqual({ accessToken: "padded-token" });

    await saveAccessToken("  ");
    expect(storage.snapshot()).toEqual({});

    await saveAccessToken("test-access-token");
    await clearAuthState();
    expect(storage.snapshot()).toEqual({});
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
