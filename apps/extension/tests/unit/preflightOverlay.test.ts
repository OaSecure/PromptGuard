import { describe, expect, it } from "vitest";
import { createPreflightOverlay } from "../../src/content/preflightOverlay";

describe("preflight overlay", () => {
  it("can initialize at document_start before document.body exists", () => {
    const doc = document.implementation.createHTMLDocument("PromptGuard early page");
    doc.body.remove();

    const overlay = createPreflightOverlay(doc);
    overlay.show({ decision: "analyzing", message: "Inspecting prompt before send.", actions: [] });

    const container = doc.getElementById("promptguard-preflight-overlay");
    expect(container).not.toBeNull();
    expect(container?.parentElement).toBe(doc.documentElement);
    expect(container?.dataset.promptguardDecision).toBe("analyzing");

    overlay.destroy();
  });
});
