import { beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_CONFIG, STORAGE_KEYS } from "../../src/shared/constants";

describe("options page", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
    document.body.innerHTML = `
      <input id="apiBaseUrl" />
      <input id="mockMode" type="checkbox" />
      <input id="token" />
      <button id="saveSettings">Save</button>
      <button id="testConnection">Test connection</button>
      <button id="syncConfig">Sync config</button>
      <div id="connectionStatus"></div>
      <div id="serverStatus"></div>
      <div id="modeStatus"></div>
      <div id="policyVersion"></div>
      <div id="fileInspection"></div>
      <div id="lastConfigSync"></div>
    `;
  });

  it("falls back to default config rendering when cached config is malformed", async () => {
    const chromeMock = createChromeMock({
      [STORAGE_KEYS.configCache]: { policy_version: "v-malformed-cache" }
    });
    vi.stubGlobal("chrome", chromeMock);

    await import("../../src/options/options");

    await waitFor(() => inputValue("#apiBaseUrl") === DEFAULT_CONFIG.api_base_url);
    expect(textValue("#policyVersion")).toBe(DEFAULT_CONFIG.policy_version);
    expect(textValue("#fileInspection")).toBe("Enabled");
    expect(textValue("#modeStatus")).toBe("Mock API");
  });

  it("trims API URL and auth token before save", async () => {
    const chromeMock = createChromeMock({});
    vi.stubGlobal("chrome", chromeMock);
    await import("../../src/options/options");

    await waitFor(() => inputValue("#apiBaseUrl") === DEFAULT_CONFIG.api_base_url);
    setInputValue("#apiBaseUrl", "  https://api.promptguard.test/api/v1  ");
    setInputValue("#token", "  padded-token  ");
    document.querySelector<HTMLButtonElement>("#saveSettings")!.click();

    await waitFor(() => chromeMock.runtime.sendMessage.mock.calls.length === 1);
    expect(chromeMock.storage.local.snapshot()[STORAGE_KEYS.apiBaseUrl]).toBe("https://api.promptguard.test/api/v1");
    expect(chromeMock.runtime.sendMessage).toHaveBeenCalledWith({
      type: "AUTH_LOGIN_REQUEST",
      payload: { token: "padded-token" }
    });
    expect(inputValue("#token")).toBe("");
    expect(textValue("#modeStatus")).toBe("Mock API");
    expect(textValue("#serverStatus")).toBe("Not checked after settings change");
  });

  it("save clears a stale server status after mode changes", async () => {
    const chromeMock = createChromeMock({ [STORAGE_KEYS.mockMode]: false });
    vi.stubGlobal("chrome", chromeMock);
    document.querySelector<HTMLElement>("#serverStatus")!.textContent = "Connected";
    await import("../../src/options/options");

    await waitFor(() => inputValue("#apiBaseUrl") === DEFAULT_CONFIG.api_base_url);
    document.querySelector<HTMLInputElement>("#mockMode")!.checked = true;
    document.querySelector<HTMLButtonElement>("#saveSettings")!.click();

    await waitFor(() => textValue("#connectionStatus") === "Saved");
    expect(textValue("#modeStatus")).toBe("Mock API");
    expect(textValue("#serverStatus")).toBe("Not checked after settings change");
  });

  it("test connection click persists visible settings and renders auth status", async () => {
    const chromeMock = createChromeMock(
      {
        [STORAGE_KEYS.mockMode]: false
      },
      async (message) =>
        message.type === "AUTH_ME_REQUEST"
          ? {
              id: "mock_user",
              workspace_id: "mock_workspace",
              email: "member@example.com",
              role: "USER",
              status: "ACTIVE"
            }
          : { ok: true }
    );
    vi.stubGlobal("chrome", chromeMock);
    await import("../../src/options/options");

    await waitFor(() => inputValue("#apiBaseUrl") === DEFAULT_CONFIG.api_base_url);
    document.querySelector<HTMLInputElement>("#mockMode")!.checked = true;
    setInputValue("#apiBaseUrl", "  https://api.promptguard.test/api/v1  ");
    document.querySelector<HTMLButtonElement>("#testConnection")!.click();

    expect(textValue("#connectionStatus")).toBe("Testing connection...");
    await waitFor(() => textValue("#connectionStatus") === "ACTIVE (USER)");
    expect(textValue("#serverStatus")).toBe("Mock API ready");
    expect(textValue("#policyVersion")).toBe(DEFAULT_CONFIG.policy_version);
    expect(chromeMock.storage.local.snapshot()[STORAGE_KEYS.mockMode]).toBe(true);
    expect(chromeMock.storage.local.snapshot()[STORAGE_KEYS.apiBaseUrl]).toBe("https://api.promptguard.test/api/v1");
  });

  it("test connection renders safe error feedback and restores the button", async () => {
    const chromeMock = createChromeMock(
      {},
      async (message) => (message.type === "AUTH_ME_REQUEST" ? { code: "NETWORK_ERROR", message: "Network error prevented inspection." } : { ok: true })
    );
    vi.stubGlobal("chrome", chromeMock);
    await import("../../src/options/options");

    await waitFor(() => inputValue("#apiBaseUrl") === DEFAULT_CONFIG.api_base_url);
    const button = document.querySelector<HTMLButtonElement>("#testConnection")!;
    button.click();

    expect(button.disabled).toBe(true);
    expect(button.textContent).toBe("Testing...");
    await waitFor(() => textValue("#connectionStatus") === "Network error prevented inspection.");
    expect(textValue("#serverStatus")).toBe("Unavailable");
    expect(button.disabled).toBe(false);
    expect(button.textContent).toBe("Test connection");
  });

  it("sync config click persists visible settings and renders returned config", async () => {
    const syncedConfig = {
      ...DEFAULT_CONFIG,
      policy_version: "v-synced",
      file_upload: { ...DEFAULT_CONFIG.file_upload, enabled: false }
    };
    const chromeMock = createChromeMock(
      {},
      async (message) => (message.type === "CONFIG_SYNC_REQUEST" ? syncedConfig : { ok: true })
    );
    vi.stubGlobal("chrome", chromeMock);
    await import("../../src/options/options");

    await waitFor(() => inputValue("#apiBaseUrl") === DEFAULT_CONFIG.api_base_url);
    document.querySelector<HTMLInputElement>("#mockMode")!.checked = false;
    setInputValue("#apiBaseUrl", "  https://api.promptguard.test/api/v1  ");
    const button = document.querySelector<HTMLButtonElement>("#syncConfig")!;
    button.click();

    expect(textValue("#connectionStatus")).toBe("Syncing config...");
    expect(button.disabled).toBe(true);
    await waitFor(() => textValue("#connectionStatus") === "Config synced");
    expect(textValue("#policyVersion")).toBe("v-synced");
    expect(textValue("#fileInspection")).toBe("Disabled");
    expect(textValue("#serverStatus")).toBe("Connected");
    expect(textValue("#modeStatus")).toBe("Real API");
    expect(button.disabled).toBe(false);
    expect(button.textContent).toBe("Sync config");
    expect(chromeMock.storage.local.snapshot()[STORAGE_KEYS.mockMode]).toBe(false);
    expect(chromeMock.storage.local.snapshot()[STORAGE_KEYS.apiBaseUrl]).toBe("https://api.promptguard.test/api/v1");
  });
});

function createChromeMock(initial: Record<string, unknown>, responder: (message: { type: string }) => Promise<unknown> = async () => ({ ok: true })) {
  const values = { ...initial };
  return {
    storage: {
      local: {
        async get(keys: string | string[]) {
          if (Array.isArray(keys)) {
            return Object.fromEntries(keys.map((key) => [key, values[key]]));
          }
          return { [keys]: values[keys] };
        },
        async set(entries: Record<string, unknown>) {
          Object.assign(values, entries);
        },
        snapshot() {
          return { ...values };
        }
      }
    },
    runtime: {
      sendMessage: vi.fn(responder)
    }
  };
}

function inputValue(selector: string): string {
  return document.querySelector<HTMLInputElement>(selector)!.value;
}

function setInputValue(selector: string, value: string): void {
  document.querySelector<HTMLInputElement>(selector)!.value = value;
}

function textValue(selector: string): string {
  return document.querySelector<HTMLElement>(selector)!.textContent ?? "";
}

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (predicate()) {
      return;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 5));
  }
  expect(predicate()).toBe(true);
}
