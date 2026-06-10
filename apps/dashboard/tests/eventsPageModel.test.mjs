import test from "node:test";
import assert from "node:assert/strict";

const {
  buildEventDetailHref,
  deriveEventsScreenState,
  projectEventTableRows,
  safeEventsErrorMessage,
} = await import("../static/eventsPageModel.js");

test("projectEventTableRows maps metadata-only event fields", () => {
  const rows = projectEventTableRows([
    {
      event_id: "evt-1",
      created_at: "2026-06-10T12:00:00Z",
      login_id: "alice",
      username: "Alice Kim",
      service: "ChatGPT",
      platform: "web",
      action: "MASK",
      risk_score: 77,
      risk_level: "high",
      primary_detection_category: "PII",
      primary_detection_type: "EMAIL",
      detection_count: 2,
      input_count: 3,
      content_unavailable_count: 1,
      detail_available: true,
    },
  ]);

  assert.equal(rows.length, 1);
  assert.deepEqual(
    rows[0].cells.map((cell) => cell.key),
    [
      "created_at",
      "username",
      "service",
      "action",
      "risk_level",
      "primary_detection_type",
      "input_count",
      "content_unavailable_count",
    ],
  );
  assert.equal(rows[0].cells[1].text, "Alice Kim");
  assert.equal(rows[0].cells[6].text, "3");
  assert.equal(rows[0].cells[7].text, "1");
  assert.equal(rows[0].detailHref, "./event-detail.html?event_id=evt-1");
});

test("projectEventTableRows falls back safely for missing optional metadata", () => {
  const rows = projectEventTableRows([
    {
      event_id: "evt-2",
      created_at: "invalid-date",
      login_id: "bob",
      username: "Bob",
      service: null,
      platform: null,
      action: "ALLOW",
      risk_score: 0,
      risk_level: "low",
      primary_detection_category: null,
      primary_detection_type: null,
      detection_count: 0,
      input_count: 0,
      content_unavailable_count: 0,
      detail_available: true,
    },
  ]);

  assert.equal(rows[0].cells[0].text, "-");
  assert.equal(rows[0].cells[2].text, "-");
  assert.equal(rows[0].cells[5].text, "-");
});

test("buildEventDetailHref encodes event ids safely", () => {
  assert.equal(buildEventDetailHref("evt/with space"), "./event-detail.html?event_id=evt%2Fwith%20space");
});

test("deriveEventsScreenState returns loading, empty, ready, and error states", () => {
  assert.deepEqual(deriveEventsScreenState("loading", 0), {
    kind: "loading",
    message: "이벤트 목록을 불러오는 중입니다.",
  });
  assert.deepEqual(deriveEventsScreenState("ready", 0), {
    kind: "empty",
    message: "표시할 이벤트가 없습니다.",
  });
  assert.deepEqual(deriveEventsScreenState("ready", 2), {
    kind: "ready",
    message: "",
  });
  assert.deepEqual(deriveEventsScreenState("error", 0), {
    kind: "error",
    message: "이벤트 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
  });
});

test("safeEventsErrorMessage stays generic and does not leak backend details", () => {
  assert.equal(safeEventsErrorMessage(401), "대시보드 로그인이 필요합니다.");
  assert.equal(safeEventsErrorMessage(403), "대시보드 접근 권한을 확인할 수 없습니다.");
  assert.equal(safeEventsErrorMessage(0), "대시보드 API에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
  assert.equal(safeEventsErrorMessage(500), "이벤트 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.");
});
