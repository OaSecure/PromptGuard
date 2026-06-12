import test from "node:test";
import assert from "node:assert/strict";

const {
  authFailureMessagePlacement,
  markProtectedDashboardReady,
  nextProtectedPageAuthState,
  runDashboardLogout,
  shouldRedirectAfterLogout,
} = await import("../static/dashboardSessionFlow.js");

test("protected dashboard pages block usable content until auth is verified", () => {
  assert.deepEqual(nextProtectedPageAuthState("loading", null), {
    contentVisible: false,
    redirectToLogin: false,
    message: "대시보드 세션을 확인하고 있습니다.",
  });

  assert.deepEqual(nextProtectedPageAuthState("error", 401), {
    contentVisible: false,
    redirectToLogin: true,
    message: "대시보드 로그인이 필요합니다.",
  });

  assert.deepEqual(nextProtectedPageAuthState("ready", null), {
    contentVisible: true,
    redirectToLogin: false,
    message: "",
  });
});

test("logout redirects only after the server confirms session revocation", () => {
  assert.equal(shouldRedirectAfterLogout("success"), true);
  assert.equal(shouldRedirectAfterLogout("csrf_failed"), false);
  assert.equal(shouldRedirectAfterLogout("network_failed"), false);
});

test("auth failure messages are scoped to the page message region, not injected above the shell", () => {
  assert.deepEqual(authFailureMessagePlacement(403), {
    target: "page-message",
    role: "alert",
    message: "대시보드 권한 또는 보안 토큰을 확인할 수 없습니다. 다시 로그인해 주세요.",
  });
});

test("runDashboardLogout redirects after success and stays on page after failure", async () => {
  const successCalls = [];
  await runDashboardLogout({
    logout: async () => {
      successCalls.push("logout");
    },
    redirectToLogin: () => {
      successCalls.push("redirect");
    },
    showError: (message) => {
      successCalls.push(`error:${message.message}`);
    },
  });
  assert.deepEqual(successCalls, ["logout", "redirect"]);

  const failureCalls = [];
  await runDashboardLogout({
    logout: async () => {
      failureCalls.push("logout");
      throw new Error("csrf failed");
    },
    redirectToLogin: () => {
      failureCalls.push("redirect");
    },
    showError: (message) => {
      failureCalls.push(`error:${message.message}`);
    },
  });
  assert.deepEqual(failureCalls, [
    "logout",
    "error:대시보드 권한 또는 보안 토큰을 확인할 수 없습니다. 다시 로그인해 주세요.",
  ]);
});

test("protected dashboard content becomes visible only after session-backed data is ready", () => {
  const removed = [];
  markProtectedDashboardReady({
    classList: {
      remove: (name) => removed.push(name),
    },
  });

  assert.deepEqual(removed, ["dashboard-auth-pending"]);
});
