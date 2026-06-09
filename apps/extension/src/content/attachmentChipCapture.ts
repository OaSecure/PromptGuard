import { createAttachmentMetadataInput, createUnsupportedAttachmentInput } from "../shared/analyzeRequestBuilder";
import type { AnalyzeInput } from "../shared/types";

/** Selector set used to find service-rendered attachment chips. */
export interface AttachmentChipSelectors {
  attachment_chip: string[];
}

/**
 * Narrows attachment-chip scanning to the current send-attempt region.
 *
 * The send attempt is scoped to the active composer container first. When the
 * page does not expose a stable composer container, the fallback stays local
 * to the input's parent branch instead of scanning the full document.
 */
export function resolveAttachmentChipScope(anchor: Element, fallbackRoot: ParentNode = document): ParentNode {
  return (
    anchor.closest("[data-promptguard-composer-root], [data-testid='composer-root'], [data-testid='composer'], form, [role='form']") ??
    anchor.parentElement ??
    fallbackRoot
  );
}

/**
 * Collects metadata-only attachment inputs from service-rendered chip DOM.
 *
 * This path is used only when the page already exposes attachment chips and
 * the extension does not hold a raw `File` object for those attachments.
 * The collector prefers safe metadata attributes and falls back to
 * `unsupported_attachment` when metadata is too weak to classify.
 */
export function collectAttachmentChipInputs(root: ParentNode = document, selectors: AttachmentChipSelectors): AnalyzeInput[] {
  const chips = uniqueChipElements(root, selectors.attachment_chip);
  return chips.map((chip, index) => buildAttachmentInput(chip, index));
}

function uniqueChipElements(root: ParentNode, selectors: string[]): HTMLElement[] {
  const seen = new Set<HTMLElement>();
  for (const selector of selectors) {
    for (const element of root.querySelectorAll<HTMLElement>(selector)) {
      seen.add(element);
    }
  }
  return [...seen];
}

function buildAttachmentInput(element: HTMLElement, attachmentIndex: number): AnalyzeInput {
  const extension = readStringAttribute(element, [
    "data-promptguard-extension",
    "data-extension",
    "data-file-extension",
    "data-file-ext"
  ]);
  const mimeType = readStringAttribute(element, [
    "data-promptguard-mime",
    "data-mime",
    "data-mime-type",
    "data-content-type"
  ]);
  const sizeBytes = readIntegerAttribute(element, [
    "data-promptguard-size-bytes",
    "data-size-bytes",
    "data-attachment-size-bytes"
  ]);
  const attachmentKind = inferAttachmentKind(element, mimeType);

  if (extension || mimeType || sizeBytes > 0 || attachmentKind === "image") {
    return createAttachmentMetadataInput({
      extension: extension || "",
      mimeType: mimeType || fallbackMimeType(attachmentKind),
      sizeBytes,
      attachmentKind,
      attachmentIndex
    });
  }

  return createUnsupportedAttachmentInput({
    extension: "",
    mimeType: "",
    sizeBytes,
    attachmentIndex
  });
}

function inferAttachmentKind(element: HTMLElement, mimeType: string): string {
  const explicitKind = readStringAttribute(element, ["data-promptguard-attachment-kind", "data-attachment-kind"]);
  if (explicitKind) {
    return explicitKind;
  }
  if (mimeType.startsWith("image/")) {
    return "image";
  }
  if (element.querySelector("img, picture, canvas, svg")) {
    return "image";
  }
  const label = [element.getAttribute("aria-label"), element.getAttribute("title")].filter(Boolean).join(" ").toLowerCase();
  if (label.includes("image") || label.includes("photo") || label.includes("screenshot")) {
    return "image";
  }
  return "file";
}

function fallbackMimeType(attachmentKind: string): string {
  return attachmentKind === "image" ? "image/unknown" : "application/octet-stream";
}

function readStringAttribute(element: HTMLElement, names: string[]): string {
  for (const name of names) {
    const value = element.getAttribute(name)?.trim();
    if (value) {
      return value;
    }
  }
  return "";
}

function readIntegerAttribute(element: HTMLElement, names: string[]): number {
  for (const name of names) {
    const value = element.getAttribute(name)?.trim();
    if (!value) {
      continue;
    }
    const parsed = Number.parseInt(value, 10);
    if (Number.isFinite(parsed) && parsed >= 0) {
      return parsed;
    }
  }
  return 0;
}
