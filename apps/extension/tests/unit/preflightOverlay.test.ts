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

  it("uses distinct alert tones for warn, mask, and block states", () => {
    const overlay = createPreflightOverlay(document);

    overlay.show({ decision: "warn", message: "확인하세요.", evidence: ["경고"], actions: [] });
    const warnContainer = document.getElementById("promptguard-preflight-overlay");
    const warnEvidence = warnContainer?.querySelector("li") as HTMLElement | null;
    const warnBorder = warnContainer?.style.border;
    const warnBackground = warnEvidence?.style.background;
    const warnIcon = warnContainer?.querySelector("[data-promptguard-icon='warn']")?.textContent;

    overlay.show({ decision: "mask", message: "대체문이 준비됐습니다.", evidence: ["마스킹"], actions: [] });
    const maskContainer = document.getElementById("promptguard-preflight-overlay");
    const maskEvidence = maskContainer?.querySelector("li") as HTMLElement | null;
    const maskBorder = maskContainer?.style.border;
    const maskBackground = maskEvidence?.style.background;
    const maskIcon = maskContainer?.querySelector("[data-promptguard-icon='mask']")?.textContent;

    overlay.show({ decision: "block", message: "전송이 중지됐습니다.", evidence: ["차단"], actions: [] });
    const blockContainer = document.getElementById("promptguard-preflight-overlay");
    const blockEvidence = blockContainer?.querySelector("li") as HTMLElement | null;
    const blockBorder = blockContainer?.style.border;
    const blockBackground = blockEvidence?.style.background;
    const blockIcon = blockContainer?.querySelector("[data-promptguard-icon='block']")?.textContent;

    expect(warnBorder).not.toBe(maskBorder);
    expect(maskBorder).not.toBe(blockBorder);
    expect(warnBackground).not.toBe(maskBackground);
    expect(maskBackground).not.toBe(blockBackground);
    expect(warnIcon).toBe("!");
    expect(maskIcon).toBe("◐");
    expect(blockIcon).toBe("×");
    overlay.destroy();
  });
});
