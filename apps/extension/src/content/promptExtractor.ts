export type PromptInputElement = HTMLTextAreaElement | HTMLElement;

export function isPromptInputElement(element: Element | null): element is PromptInputElement {
  if (!element) {
    return false;
  }
  if (element instanceof HTMLTextAreaElement) {
    return true;
  }
  return element instanceof HTMLElement && (element.isContentEditable || element.getAttribute("contenteditable") === "true");
}

export function extractPromptText(element: PromptInputElement): string {
  if (element instanceof HTMLTextAreaElement) {
    return element.value;
  }
  return element.innerText || element.textContent || "";
}

export function setPromptText(element: PromptInputElement, value: string): void {
  if (element instanceof HTMLTextAreaElement) {
    element.value = value;
    element.dispatchEvent(new Event("input", { bubbles: true }));
    return;
  }
  element.textContent = value;
  element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
}
