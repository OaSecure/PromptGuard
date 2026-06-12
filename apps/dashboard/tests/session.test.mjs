import test from "node:test";
import assert from "node:assert/strict";

const { createDashboardSessionClient } = await import("../static/session.js");

test("logout refreshes session csrf when only stale cookie fallback is available", async () => {
  const calls = [];
  const client = createDashboardSessionClient({
    cookieToken: () => "stale-cookie-token",
    request: async (path, options = {}) => {
      calls.push({ path, options });
      if (path === "/dashboard/session/csrf") return { csrf_token: "fresh-session-token" };
      return {};
    },
  });

  await client.logoutDashboardSession();

  assert.deepEqual(calls.map((call) => call.path), ["/dashboard/session/csrf", "/dashboard/session/logout"]);
  assert.equal(calls[1].options.csrfToken, "fresh-session-token");
});

test("logout uses login response csrf token while it is still cached", async () => {
  const calls = [];
  const client = createDashboardSessionClient({
    cookieToken: () => "stale-cookie-token",
    request: async (path, options = {}) => {
      calls.push({ path, options });
      if (path === "/dashboard/session/csrf") return { csrf_token: "login-csrf-token" };
      if (path === "/dashboard/session/login") {
        return {
          ok: true,
          user: { id: "1", login_id: "admin", username: "Admin", department: null, display_name: null, role: "ADMIN", status: "ACTIVE" },
          csrf_token: "session-csrf-token",
          expires_at: "2026-06-12T00:00:00Z",
        };
      }
      return {};
    },
  });

  await client.loginDashboardSession("admin", "1234");
  await client.logoutDashboardSession();

  assert.deepEqual(calls.map((call) => call.path), [
    "/dashboard/session/csrf",
    "/dashboard/session/login",
    "/dashboard/session/logout",
  ]);
  assert.equal(calls[2].options.csrfToken, "session-csrf-token");
});
