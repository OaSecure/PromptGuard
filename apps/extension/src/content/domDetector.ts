import { isPromptInputElement, type PromptInputElement } from "./promptExtractor";

export interface DetectorSelectors {
  input: string[];
}

export interface InputCandidate {
  element: PromptInputElement;
  score: number;
  reason: string[];
}

export function findBestInputCandidate(root: ParentNode = document, selectors: DetectorSelectors = { input: ["textarea", "[contenteditable='true']"] }): InputCandidate | null {
  const candidates = selectors.input
    .flatMap((selector) => Array.from(root.querySelectorAll(selector)))
    .filter(isPromptInputElement)
    .map(scoreInputCandidate)
    .filter((candidate) => candidate.score > 0)
    .sort((a, b) => b.score - a.score);

  return candidates[0] ?? null;
}

export function scoreInputCandidate(element: PromptInputElement): InputCandidate {
  const reason: string[] = [];
  let score = 0;

  if (isVisible(element)) {
    score += 30;
    reason.push("visible");
  }
  if (document.activeElement === element || element.contains(document.activeElement)) {
    score += 40;
    reason.push("focused");
  }
  if (element instanceof HTMLTextAreaElement) {
    score += 15;
    reason.push("textarea");
  } else if (element.isContentEditable || element.getAttribute("contenteditable") === "true") {
    score += 15;
    reason.push("contenteditable");
  }
  if (hasUsableSize(element)) {
    score += 10;
    reason.push("sized");
  }
  if (element.getAttribute("aria-label")?.toLowerCase().includes("prompt")) {
    score += 5;
    reason.push("aria-prompt");
  }

  return { element, score, reason };
}

function isVisible(element: HTMLElement): boolean {
  const style = window.getComputedStyle(element);
  if (style.visibility === "hidden" || style.display === "none" || Number(style.opacity) === 0) {
    return false;
  }
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function hasUsableSize(element: HTMLElement): boolean {
  const rect = element.getBoundingClientRect();
  return rect.width >= 40 && rect.height >= 16;
}
