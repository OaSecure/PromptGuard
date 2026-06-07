import test from "node:test";
import assert from "node:assert/strict";

const {
  buildCreateUserRequest,
  buildUpdateUserRoleRequest,
  buildUpdateUserStatusRequest,
  shouldRedirectUsersScreen,
} = await import("../static/usersRequestModel.js");

test("buildCreateUserRequest uses the documented users path and csrf token", () => {
  const request = buildCreateUserRequest(
    {
      login_id: "alice",
      username: "Alice",
      password: "Secret123!",
      department: "Security",
      role: "ADMIN",
    },
    "csrf-1",
  );

  assert.deepEqual(request, {
    path: "/dashboard/users",
    options: {
      method: "POST",
      csrfToken: "csrf-1",
      body: {
        login_id: "alice",
        username: "Alice",
        password: "Secret123!",
        department: "Security",
        role: "ADMIN",
      },
    },
  });
});

test("buildUpdateUserRoleRequest uses login_id path parameter and PATCH", () => {
  const request = buildUpdateUserRoleRequest("alice@example.com", { role: "USER" }, "csrf-2");

  assert.deepEqual(request, {
    path: "/dashboard/users/alice%40example.com/role",
    options: {
      method: "PATCH",
      csrfToken: "csrf-2",
      body: { role: "USER" },
    },
  });
});

test("buildUpdateUserStatusRequest uses login_id path parameter and PATCH", () => {
  const request = buildUpdateUserStatusRequest("alice", { status: "DISABLED" }, "csrf-3");

  assert.deepEqual(request, {
    path: "/dashboard/users/alice/status",
    options: {
      method: "PATCH",
      csrfToken: "csrf-3",
      body: { status: "DISABLED" },
    },
  });
});

test("shouldRedirectUsersScreen redirects only for session and permission failures", () => {
  assert.equal(shouldRedirectUsersScreen(401), true);
  assert.equal(shouldRedirectUsersScreen(403), true);
  assert.equal(shouldRedirectUsersScreen(400), false);
  assert.equal(shouldRedirectUsersScreen(404), false);
  assert.equal(shouldRedirectUsersScreen(500), false);
});
