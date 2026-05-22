import { isPromptInputElement, type PromptInputElement } from "./promptExtractor";
import type { PromptInputMethod } from "../shared/types";

export interface SendAttempt {
  method: PromptInputMethod;
  target: EventTarget | null;
}

export interface SendInterceptorOptions {
  document?: Document;
  sendButtonSelectors: string[];
  getPromptInput: () => PromptInputElement | null;
  onSendAttempt: (attempt: SendAttempt) => void;
  shouldBypass?: () => boolean;
}

export interface SendInterceptor {
  disconnect(): void;
}

export function keyboardSendMethod(event: Pick<KeyboardEvent, "key" | "shiftKey" | "ctrlKey" | "altKey" | "metaKey" | "isComposing">): PromptInputMethod | null {
  if (event.key !== "Enter") {
    return null;
  }
  if (event.shiftKey || event.ctrlKey || event.altKey || event.metaKey || event.isComposing) {
    return null;
  }
  return "ENTER";
}

export function installSendInterceptor(options: SendInterceptorOptions): SendInterceptor {
  const doc = options.document ?? document;

  const clickHandler = (event: MouseEvent): void => {
    if (options.shouldBypass?.()) {
      return;
    }
    const target = event.target instanceof Element ? event.target : null;
    if (!target || !matchesAnySelector(target, options.sendButtonSelectors)) {
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    options.onSendAttempt({ method: "CLICK", target: event.target });
  };

  const keydownHandler = (event: KeyboardEvent): void => {
    if (options.shouldBypass?.()) {
      return;
    }
    const method = keyboardSendMethod(event);
    if (!method) {
      return;
    }
    const input = options.getPromptInput();
    if (!input || !eventTargetsPromptInput(event.target, input)) {
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    options.onSendAttempt({ method, target: event.target });
  };

  doc.addEventListener("click", clickHandler, true);
  doc.addEventListener("keydown", keydownHandler, true);

  return {
    disconnect() {
      doc.removeEventListener("click", clickHandler, true);
      doc.removeEventListener("keydown", keydownHandler, true);
    }
  };
}

export function replaySendAttempt(doc: Document, sendButtonSelectors: string[]): boolean {
  const button = findSendButton(doc, sendButtonSelectors);
  if (!button) {
    return false;
  }
  button.click();
  return true;
}

function findSendButton(doc: Document, selectors: string[]): HTMLButtonElement | null {
  for (const selector of selectors) {
    const element = doc.querySelector(selector);
    if (element instanceof HTMLButtonElement) {
      return element;
    }
  }
  return null;
}

function matchesAnySelector(element: Element, selectors: string[]): boolean {
  return selectors.some((selector) => element.matches(selector) || Boolean(element.closest(selector)));
}

function eventTargetsPromptInput(target: EventTarget | null, input: PromptInputElement): boolean {
  if (!isPromptInputElement(input)) {
    return false;
  }
  if (target === input) {
    return true;
  }
  return target instanceof Node && input.contains(target);
}
