import { filesFromFileList, type FileUploadAttempt } from "./fileUploadSnapshot";

/**
 * Configures DOM listeners that pause native file attach attempts.
 *
 * `shouldBypass` lets the controller replay an approved input-change attempt
 * without the extension immediately intercepting its own replay.
 */
export interface FileUploadInterceptorOptions {
  document?: Document;
  fileInputSelectors: string[];
  dropZoneSelectors: string[];
  onFileAttempt: (attempt: FileUploadAttempt) => void;
  shouldBypass?: () => boolean;
}

/** Owns the lifecycle of file upload listeners installed on the page. */
export interface FileUploadInterceptor {
  disconnect(): void;
}

/**
 * Installs capture-phase listeners for file input changes and drag/drop files.
 *
 * The interceptor only stops events that actually contain files and match the
 * configured surfaces, so unrelated page changes and non-file drops continue
 * through the page normally.
 */
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

/**
 * Replays an approved file input change when browser state still allows it.
 *
 * Drag/drop attempts cannot be replayed safely because browsers do not allow
 * scripts to recreate a trusted `DataTransfer` file drop. Those cases return
 * `false` so the controller can show the reattach fallback.
 */
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
