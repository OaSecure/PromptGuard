import { describe, expect, it } from "vitest";
import { createPreflightOverlay } from "../../src/content/preflightOverlay";

describe("preflight overlay", () => {
  it("can initialize at document_start before document.body exists", () => {
    const doc = document.implementation.createHTMLDocument("PromptGuard early page");
    doc.body.remove();

    const overlay = createPreflightOverlay(doc);
    overlay.show({ decision: "analyzing", message: "전송 전 검사 중입니다.", actions: [] });

    const container = doc.getElementById("promptguard-preflight-overlay");
    expect(container).not.toBeNull();
    expect(container?.parentElement).toBe(doc.documentElement);
    expect(container?.dataset.promptguardDecision).toBe("analyzing");

    overlay.destroy();
  });

  it("renders warning evidence with a status icon and readable title", () => {
    const overlay = createPreflightOverlay(document);

    overlay.show({
      decision: "warn",
      message: "전송 전 확인하세요.",
      evidence: ["탐지: 기밀 비즈니스 정보"],
      actions: []
    });

    const container = document.getElementById("promptguard-preflight-overlay");
    expect(container?.textContent).toContain("주의: 검토 필요");
    expect(container?.textContent).toContain("탐지: 기밀 비즈니스 정보");
    expect(container?.querySelector("[data-promptguard-icon='warn']")?.textContent).toBe("!");
    overlay.destroy();
  });
});
