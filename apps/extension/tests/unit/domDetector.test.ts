import { describe, expect, it } from "vitest";
import { findBestInputCandidate } from "../../src/content/domDetector";
import { extractPromptText, setPromptText } from "../../src/content/promptExtractor";

describe("DOM input detection", () => {
  it("selects a visible textarea and extracts text", () => {
    document.body.innerHTML = `<textarea style="width: 240px; height: 48px">hello</textarea>`;
    const textarea = document.querySelector("textarea");
    mockRect(textarea!);
    textarea?.focus();

    const candidate = findBestInputCandidate(document);

    expect(candidate?.element).toBe(textarea);
    expect(candidate?.score).toBeGreaterThan(0);
    expect(extractPromptText(candidate!.element)).toBe("hello");
  });

  it("supports contenteditable replacement without automatic submit", () => {
    document.body.innerHTML = `<div contenteditable="true" style="width: 240px; height: 48px">before</div>`;
    mockRect(document.querySelector("[contenteditable='true']")!);
    const candidate = findBestInputCandidate(document);

    setPromptText(candidate!.element, "[masked]");

    expect(extractPromptText(candidate!.element)).toBe("[masked]");
  });
});

function mockRect(element: Element): void {
  Object.defineProperty(element, "getBoundingClientRect", {
    value: () => ({ width: 240, height: 48, top: 0, left: 0, right: 240, bottom: 48, x: 0, y: 0, toJSON: () => ({}) }),
    configurable: true
  });
}
