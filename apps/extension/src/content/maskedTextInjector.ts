import { setPromptText, type PromptInputElement } from "./promptExtractor";

export interface MaskApplyResult {
  applied: boolean;
  reason?: "EMPTY_MASK" | "UNSUPPORTED_INPUT";
}

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
