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
      "primary_detection_category",
      "primary_detection_type",
      "detection_count",
      "input_count",
      "content_unavailable_count",
      "detail",
    ],
  );
  assert.equal(rows[0].cells[1].text, "Alice Kim");
  assert.equal(rows[0].cells[5].text, "PII");
  assert.equal(rows[0].cells[6].text, "EMAIL");
  assert.equal(rows[0].cells[7].text, "2");
  assert.equal(rows[0].cells[8].text, "3");
  assert.equal(rows[0].cells[9].text, "1");
  assert.equal(rows[0].cells[10].text, "상세보기");
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
  assert.equal(rows[0].cells[6].text, "-");
  assert.equal(rows[0].cells[10].text, "상세보기");
});

test("buildEventDetailHref encodes event ids safely", () => {
  assert.equal(buildEventDetailHref("evt/with space"), "./event-detail.html?event_id=evt%2Fwith%20space");
});

test("deriveEventsScreenState returns loading, empty, ready, and error states", () => {
  assert.deepEqual(deriveEventsScreenState("loading", 0), {
    kind: "loading",
    message: "데이터를 불러오는 중입니다.",
  });
  assert.deepEqual(deriveEventsScreenState("ready", 0), {
    kind: "empty",
    message: "표시할 데이터가 없습니다.",
  });
  assert.deepEqual(deriveEventsScreenState("ready", 2), {
    kind: "ready",
    message: "",
  });
  assert.deepEqual(deriveEventsScreenState("error", 0), {
    kind: "error",
    message: "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
  });
});

test("safeEventsErrorMessage stays generic and does not leak backend details", () => {
  assert.equal(safeEventsErrorMessage(401), "대시보드 로그인이 필요합니다.");
  assert.equal(safeEventsErrorMessage(403), "대시보드 로그인이 필요합니다.");
  assert.equal(safeEventsErrorMessage(0), "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
  assert.equal(safeEventsErrorMessage(500), "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.");
});
