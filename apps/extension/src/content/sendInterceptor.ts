import { isPromptInputElement, type PromptInputElement } from "./promptExtractor";
import type { PromptInputMethod } from "../shared/types";

/** Describes a user action that may send the current prompt. */
export interface SendAttempt {
  method: PromptInputMethod;
  target: EventTarget | null;
}

/**
 * Configures DOM listeners that pause native prompt sends.
 *
 * `shouldBypass` is used during a guarded replay so the extension can hand the
 * already-approved action back to the page without inspecting its own replay.
 */
export interface SendInterceptorOptions {
  document?: Document;
  sendButtonSelectors: string[];
  getPromptInput: () => PromptInputElement | null;
  onSendAttempt: (attempt: SendAttempt) => void;
  shouldBypass?: () => boolean;
}

/** Owns the lifecycle of prompt send listeners installed on the page. */
export interface SendInterceptor {
  disconnect(): void;
}

/**
 * Classifies a keyboard event as an Enter-based send attempt.
 *
 * Modified Enter combinations and IME composition are treated as text entry so
 * PromptGuard does not block normal multiline or composing-input behavior.
 */
export function keyboardSendMethod(event: Pick<KeyboardEvent, "key" | "shiftKey" | "ctrlKey" | "altKey" | "metaKey" | "isComposing">): PromptInputMethod | null {
  if (event.key !== "Enter") {
    return null;
  }
  if (event.shiftKey || event.ctrlKey || event.altKey || event.metaKey || event.isComposing) {
    return null;
  }
  return "ENTER";
}

/**
 * Installs capture-phase listeners for click and Enter send attempts.
 *
 * The listeners call `preventDefault` and `stopImmediatePropagation` only after
 * confirming that the event is a real send attempt. This preserves ordinary
 * page behavior while giving the preflight controller the first chance to
 * inspect outbound prompt text.
 */
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

/**
 * Replays the page's native send button after inspection authorizes it.
 *
 * The controller wraps this call with the replay bypass flag; without that
 * guard, this synthetic click would be captured as a new uninspected attempt.
 */
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
