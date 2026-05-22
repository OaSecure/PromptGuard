import { describe, expect, it } from "vitest";
import { applyMaskedPrompt } from "../../src/content/maskedTextInjector";
import { extractPromptText } from "../../src/content/promptExtractor";

describe("masked prompt injector", () => {
  it("replaces textarea content without submitting", () => {
    document.body.innerHTML = `<form><textarea></textarea><button type="submit">Send</button></form>`;
    const textarea = document.querySelector("textarea")!;
    let submits = 0;
    document.querySelector("form")!.addEventListener("submit", (event) => {
      event.preventDefault();
      submits += 1;
    });

    const result = applyMaskedPrompt(textarea, "[masked]");

    expect(result.applied).toBe(true);
    expect(extractPromptText(textarea)).toBe("[masked]");
    expect(submits).toBe(0);
  });

  it("replaces contenteditable content without submitting", () => {
    document.body.innerHTML = `<div contenteditable="true"></div>`;
    const editor = document.querySelector<HTMLElement>("[contenteditable='true']")!;

    const result = applyMaskedPrompt(editor, "[masked]");

    expect(result.applied).toBe(true);
    expect(extractPromptText(editor)).toBe("[masked]");
  });
});
