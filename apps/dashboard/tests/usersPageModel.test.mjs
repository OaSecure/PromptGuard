import test from "node:test";
import assert from "node:assert/strict";

const {
  projectUserTableRows,
  normalizeCreateUserPayload,
  normalizeRolePayload,
  normalizeStatusPayload,
  deriveUsersScreenState,
  safeUsersMutationErrorMessage,
} = await import("../static/usersPageModel.js");

test("projectUserTableRows maps safe dashboard user fields only", () => {
  const rows = projectUserTableRows([
    {
      login_id: "alice",
      username: "Alice",
      department: "Security",
      role: "ADMIN",
      status: "ACTIVE",
      created_at: "2026-06-08T10:00:00Z",
      last_login_at: null,
      last_event_at: null,
      event_count: 12,
      blocked_count: 2,
      masked_count: 3,
      warned_count: 1,
    },
  ]);

  assert.equal(rows.length, 1);
  assert.deepEqual(
    rows[0].cells.map((cell) => cell.key),
    [
      "login_id",
      "username",
      "department",
      "role",
      "status",
      "last_login_at",
      "last_event_at",
      "created_at",
      "event_count",
      "blocked_count",
      "masked_count",
      "warned_count",
    ],
  );
  assert.equal(rows[0].cells[0].text, "alice");
  assert.equal(rows[0].cells[3].text, "ADMIN");
  assert.equal(rows[0].cells[5].text, "-");
  assert.equal(rows[0].cells[8].text, "12");
  assert.equal(rows[0].cells.some((cell) => cell.key === "last_login_at"), true);
});

test("normalizeCreateUserPayload trims safe fields and omits empty department", () => {
  const payload = normalizeCreateUserPayload({
    loginId: " alice ",
    username: " Alice Kim ",
    password: "Secret123!",
    department: " ",
    role: "ADMIN",
  });

  assert.deepEqual(payload, {
    login_id: "alice",
    username: "Alice Kim",
    password: "Secret123!",
    role: "ADMIN",
  });
});

test("normalize role and status payloads fail closed to documented enums", () => {
  assert.deepEqual(normalizeRolePayload("ADMIN"), { role: "ADMIN" });
  assert.deepEqual(normalizeRolePayload("unexpected"), { role: "USER" });
  assert.deepEqual(normalizeStatusPayload("DISABLED"), { status: "DISABLED" });
  assert.deepEqual(normalizeStatusPayload("unexpected"), { status: "ACTIVE" });
});

test("deriveUsersScreenState returns empty and error states safely", () => {
  assert.deepEqual(deriveUsersScreenState([], false), {
    kind: "empty",
    message: "표시할 데이터가 없습니다.",
  });
  assert.deepEqual(deriveUsersScreenState([], true), {
    kind: "error",
    message: "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
  });
});

test("safeUsersMutationErrorMessage stays generic and does not leak backend details", () => {
  assert.equal(safeUsersMutationErrorMessage(400), "입력값을 확인해 주세요.");
  assert.equal(
    safeUsersMutationErrorMessage(403),
    "대시보드 권한 또는 보안 토큰을 확인할 수 없습니다. 다시 로그인해 주세요.",
  );
  assert.equal(safeUsersMutationErrorMessage(500), "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.");
});
