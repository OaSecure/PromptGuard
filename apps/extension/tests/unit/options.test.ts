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
      <button id="saveSettings"></button>
      <button id="testConnection"></button>
      <button id="syncConfig"></button>
      <div id="connectionStatus"></div>
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
  });
});

function createChromeMock(initial: Record<string, unknown>) {
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
      sendMessage: vi.fn(async () => ({ ok: true }))
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
