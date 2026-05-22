/** Supported DOM element shapes that can hold prompt text in the MVP. */
export type PromptInputElement = HTMLTextAreaElement | HTMLElement;

/**
 * Checks whether a DOM element can be treated as a prompt input.
 *
 * The MVP supports textarea and contenteditable inputs because those cover the
 * current ChatGPT-like surfaces without requiring page-specific private APIs.
 */
export function isPromptInputElement(element: Element | null): element is PromptInputElement {
  if (!element) {
    return false;
  }
  if (element instanceof HTMLTextAreaElement) {
    return true;
  }
  return element instanceof HTMLElement && (element.isContentEditable || element.getAttribute("contenteditable") === "true");
}

/**
 * Reads prompt text from a supported input element.
 *
 * Callers must treat the returned text as transient inspection input and must
 * not store or log it.
 */
export function extractPromptText(element: PromptInputElement): string {
  if (element instanceof HTMLTextAreaElement) {
    return element.value;
  }
  return element.innerText || element.textContent || "";
}

/**
 * Replaces prompt text and emits an input event for page state sync.
 *
 * Mask handling depends on the host page noticing the edited value; dispatching
 * `input` keeps React-like controlled inputs aligned with the DOM replacement.
 */
export function setPromptText(element: PromptInputElement, value: string): void {
  if (element instanceof HTMLTextAreaElement) {
    element.value = value;
    element.dispatchEvent(new Event("input", { bubbles: true }));
    return;
  }
  element.textContent = value;
  element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
}
