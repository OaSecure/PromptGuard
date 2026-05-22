import { filesFromFileList, type FileUploadAttempt } from "./fileUploadSnapshot";

export interface FileUploadInterceptorOptions {
  document?: Document;
  fileInputSelectors: string[];
  dropZoneSelectors: string[];
  onFileAttempt: (attempt: FileUploadAttempt) => void;
  shouldBypass?: () => boolean;
}

export interface FileUploadInterceptor {
  disconnect(): void;
}

export function installFileUploadInterceptor(options: FileUploadInterceptorOptions): FileUploadInterceptor {
  const doc = options.document ?? document;

  const changeHandler = (event: Event): void => {
    if (options.shouldBypass?.()) {
      return;
    }
    const input = event.target instanceof HTMLInputElement ? event.target : null;
    if (!input || input.type !== "file" || !matchesAnySelector(input, options.fileInputSelectors)) {
      return;
    }

    const files = filesFromFileList(input.files);
    if (files.length === 0) {
      return;
    }

    event.preventDefault();
    event.stopImmediatePropagation();
    options.onFileAttempt({ method: "INPUT", target: input, files });
  };

  const dropHandler = (event: DragEvent): void => {
    if (options.shouldBypass?.()) {
      return;
    }
    const files = filesFromFileList(event.dataTransfer?.files);
    if (files.length === 0) {
      return;
    }
    const target = event.target instanceof Element ? event.target : null;
    if (target && options.dropZoneSelectors.length > 0 && !matchesAnySelector(target, options.dropZoneSelectors)) {
      return;
    }

    event.preventDefault();
    event.stopImmediatePropagation();
    options.onFileAttempt({ method: "DROP", target: event.target, files });
  };

  doc.addEventListener("change", changeHandler, true);
  doc.addEventListener("drop", dropHandler, true);

  return {
    disconnect() {
      doc.removeEventListener("change", changeHandler, true);
      doc.removeEventListener("drop", dropHandler, true);
    }
  };
}

export function replayFileUploadAttempt(attempt: FileUploadAttempt): boolean {
  if (attempt.method !== "INPUT" || !(attempt.target instanceof HTMLInputElement)) {
    return false;
  }

  attempt.target.dispatchEvent(new Event("change", { bubbles: true, cancelable: true }));
  return true;
}

function matchesAnySelector(element: Element, selectors: string[]): boolean {
  return selectors.some((selector) => element.matches(selector) || Boolean(element.closest(selector)));
}
