import { setPromptText, type PromptInputElement } from "./promptExtractor";

/** Reports whether a masked prompt replacement was applied to the page. */
export interface MaskApplyResult {
  applied: boolean;
  reason?: "EMPTY_MASK" | "UNSUPPORTED_INPUT";
}

/**
 * Applies a server-provided masked prompt to the current input.
 *
 * This function deliberately edits the input only. It never triggers send; the
 * user must review the replacement and submit again manually.
 */
export function applyMaskedPrompt(element: PromptInputElement | null | undefined, maskedPrompt: string | undefined): MaskApplyResult {
  if (!maskedPrompt) {
    return { applied: false, reason: "EMPTY_MASK" };
  }
  if (!element) {
    return { applied: false, reason: "UNSUPPORTED_INPUT" };
  }

  setPromptText(element, maskedPrompt);
  return { applied: true };
}
