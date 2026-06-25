import test from "node:test";
import assert from "node:assert/strict";

const { dashboardApiBaseUrl, dashboardRequest } = await import("../static/dashboardApi.js");

function setDashboardApiBaseUrl(value) {
  globalThis.document = {
    documentElement: {
      dataset: value === undefined ? {} : { promptguardApiBaseUrl: value },
    },
  };
}

test("dashboard API base URL defaults to same origin", () => {
  setDashboardApiBaseUrl(undefined);

  assert.equal(dashboardApiBaseUrl(), "");
});

test("dashboard API base URL treats blank explicit config as same origin", () => {
  setDashboardApiBaseUrl("   ");

  assert.equal(dashboardApiBaseUrl(), "");
});

test("dashboard API base URL preserves explicit configured origin without trailing slash", () => {
  setDashboardApiBaseUrl(" https://promptguard.example.com:9443/// ");

  assert.equal(dashboardApiBaseUrl(), "https://promptguard.example.com:9443");
});

test("dashboard requests use same-origin relative path when no base URL is configured", async () => {
  const calls = [];
  setDashboardApiBaseUrl(undefined);
  globalThis.Headers = class Headers {
    set() {}
  };
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    };
  };

  const response = await dashboardRequest("/dashboard/status");

  assert.deepEqual(response, { ok: true });
  assert.equal(calls[0].url, "/dashboard/status");
  assert.equal(calls[0].options.credentials, "include");
});
